

import numpy as np

import datetime
import traceback


if __name__ == '__main__':
    import time
    import cv2

    # pipe = "rtsp://admin:admin@192.168.1.30/stream1"
    # pipe = "rtsp://localhost:8554/stream"
    pipe = "rtsp://192.168.0.208:554/stream"



    video = cv2.VideoCapture(pipe)

    time.sleep(1)
    cv2.namedWindow("test")
    ret, frames = video.read()

    while True:
        ret, frames = video.read()

        if ret :

            cv2.imshow('test', frames)

            if cv2.waitKey(1) & 0xFF == 27:
                break
        
    cv2.destroyAllWindows()