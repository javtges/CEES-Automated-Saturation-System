# Import libraries
import datetime
import time
from multiprocessing import Process

import adafruit_mcp4725
import board
import busio
import cv2
import numpy as np

from CEESClasses import Experiment


# Define functions
def initialize():
    """Initialize the following:
    1. the Raspberry Pi's I2C bus,
    2. the MCP4725 board,
    3. and the current Experiment class object
    """
    i2c = busio.I2C(board.SCL, board.SDA)

    dac = adafruit_mcp4725.MCP4725(i2c)

    """TARGET: Parallelize Experiment initialization with user input"""
    title = "ASS_v5"
    exp = Experiment(title)
    return exp, dac


def image_processing(backSub, frame, coordinates):
    """Process image to capture moving pixels.
    Crop image to region of interest (ROI), then convert to grayscalexp.
    After that use background subtraction on ROI.
    """
    north, south, east, west = coordinates

    """TARGET: Better variable names"""
    gray = cv2.cv2tColor(rect_img, cv2.COLOR_BGR2GRAY)
    fgMask = backSub.apply(gray)
    fgMask_RGB = cv2.cv2tColor(fgMask, cv2.COLOR_GRAY2RGB)

    cv2.rectangle(frame, (10, 2), (100, 20), (0, 0, 0), -1)
    cv2.putText(frame, str(capture.get(cv2.CAP_PROP_POS_FRAMES)), (15, 15),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255))

    # Replacing the sketched image on Region of Interest
    frame[north: south, west: east] = fgMask_RGB
    noise = cv2.countNonZero(fgMask)
    return frame, noise


def parallelize(function, arguments=None):
    """Parallelize functions so as to not interrupt valve operation"""
    t = Process(target=function, args=arguments)
    t.start()


def frame_set(coordinates, key):
    """Set region of interest to where drops fall using keys"""
    validKeys = [ord('w'), ord('W'), ord('a'), ord('A'),
                 ord('s'), ord('S'), ord('d'), ord('D'),
                 ord('i'), ord('I'), ord('j'), ord('J'),
                 ord('k'), ord('K'), ord('l'), ord('L'),
                 ]
    north, south, east, west = coordinates

    # Top-Right Corner
    if key == ord('w') or key == ord('W'):
        north -= 5
    elif key == ord('a') or key == ord('A'):
        west -= 5
    elif key == ord('s') or key == ord('S'):
        north += 5
    elif key == ord('d') or key == ord('D'):
        west += 5

    # Bottom-Left Corner
    elif key == ord('i') or key == ord('I'):
        south -= 5
    elif key == ord('j') or key == ord('J'):
        east -= 5
    elif key == ord('k') or key == ord('K'):
        south += 5
    elif key == ord('l') or key == ord('L'):
        east += 5

    """TARGET: Turn into bounds checking function"""
    if (north < 0):
        north = 0
    elif (north > height):
        north = height
    if (south < 0):
        south = 0
    elif (south > height):
        south = height
    if (east < 0):
        east = 0
    elif (east > width):
        east = width
    if (west < 0):
        west = 0
    elif (west > width):
        west = width
    coordinates = [north, south, east, west]

    if key in validKeys:
        print("Coordinates: ({0}, {1}), ({2}, {3})".format(*coordinates))

    return coordinates


def summary(exp):
    """ Print out essential experiment statistics"""
    print("Final voltage: {:.2f}".format(exp.get_volts()))
    print("Total drops: {}".format(exp.get_drops()))
    print("Average pixel noise: {:.2f}".format(exp.get_noise_average()))
    print("Average drop noise: {:.2f}".format(exp.get_drop_average()))


def terminationProcedure(dac, volts):
    """Completely closes the valve.
    Makes the current volts a multiple of 10. Then decreases by 5.
    Continues until the volts set to 44% the calibrated 'closed' volts.

    Valve closing is isolated from experiment object.
    """
    volts = int(volts / 10) * 10
    while (volts > 20):
        volts -= 5
        dac.raw_value = volts
        time.sleep(0.1)      


if __name__ == '__main__':
    # Initialize settings
    exp, dac = initialize()
    mutiny = success = defaults = calibration = False
    frames = waitFrame = 0
    liquid = True

    # Open video feed
    """TARGET: Parametrize video source"""
    backSub = cv2.createBackgroundSubtractorMOG2(history=40, varThreshold=60, detectShadows=False)
    capture = cv2.VideoCapture(0)  # 0 = laptop webcam; 1 = USB webcam; "cv2.samples.findFileOrKeep(args.input))" = file
    if not capture.isOpened:
        print("Unable to open 0")
        exit(1)

    # get image dimensions
    height, width = int(capture.get(4)), int(capture.get(3))
    coords = [0, height, width, 0]

    # clog values
    time_open = 0
    latency_delay = 0
    clogged = False

    while (liquid):
        # Takes frame input from camera
        ret, frame = capture.read()
        if frame is None:
            print("Camera Error")  
            exit(1)

        # Rectangle marker
        r = cv2.rectangle(frame, (coords[3], coords[0]), (coords[2], coords[1]), (100, 50, 200), 3)
        rect_img = frame[coords[0]:coords[1], coords[3]: coords[2]]

        # Main processing of program
        if (defaults):
            frames += 1
            frame, noise = image_processing(backSub, frame, coords)
            if(calibration):
                """TARGET: Better filtering of drop ripples based on continuity"""
                if(noise > pixAvg * 5):
                    if (exp.get_clog_volts() > exp.get_volts()):
                        exp.equalize_volts()
                    if (waitFrame == 0):
                        exp.add_drop(frames, noise)
                    elif (waitFrame < 10):
                        waitFrame += 1
                    else:
                        waitFrame = 0
                    time_open = 0
                    clogged = False
                else:
                    # clog protocol
                    # while there is no drop, increase voltage every 10s (to account for latency)
                    # if 60s at max voltage with no drop pass, terminate
                    if (exp.time_since_drop() > 30):
                        if (not clogged): 
                            latency_delay = time.time()
                            clogged = True
                        if (time.time() - latency_delay > 10):
                            print("{:.2f}".format(time.time() - latency_delay))
                            if (exp.get_clog_volts() == 4054):
                                time_open += 1
                            else: exp.cSet(1)
                            if (exp.get_clog_volts() >= 4055):
                                exp.cSet(4054)
                            clogged = False
                        if (time_open >= 6):
                            exp.volts(4055)
                            success = True
                            liquid = False
                    else: pixAvg = exp.addNoise(frames, noise)                   
            else: 
                mutiny = True
                dac.raw_value = 5
                time.sleep(0.01)
                if (frames < 250): 
                    pixAvg = exp.addNoise(frames, noise)  
                else: 
                    print("CALIBRATION COMPLETE")
                    mutiny = False
                    calibration = True
    
        # Show the image in a resizeable frame
        cv2.namedWindow('Frame',cv2.WINDOW_NORMAL)
        cv2.imshow('Frame', frame)      
        k = cv2.waitKey(60) & 0xFF

        # Checks for keypresses
        if ((k == ord('q')) or (k == ord('Q'))): liquid = False
        elif (k == ord('0')): defaults = exp.dSet()                        # Confirm default voltage and rectangle size and location
        elif ((k == ord('r')) or (k == ord('R'))): defaults = False      # Don't save data while default voltage and rectangle values are reset
        elif ((k == ord('c')) or (k == ord('C'))): calibration = False   # Calibration sequence restarts (100 frames to average noise level)
        elif ((k == ord('n')) or (k == ord('N'))): parallelize(exp.addNotes, (frames,)) # Insert additional notes
        elif ((k == ord('e')) or (k == ord('E'))): exp.vSet(0)
        elif (k == ord('+')): exp.vSet(1)
        elif (k == ord('-')): exp.vSet(2)
        elif (k != 0xFF): coords = frame_set(coords, k)
        
        if (not mutiny): dac.raw_value = exp.get_volts()
    capture.release()
    cv2.destroyAllWindows()
    parallelize(terminationProcedure, (exp.get_volts(),))
    exp.finalNotes()
    exp.terminate(success)
