#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Jan  20 02:07:13 2019

@author: prabhakar
Modified to continuously capture frames
"""
# import necessary argumnets 
import gi
import cv2
import argparse
import threading
import time
import queue

# import required library like Gstreamer and GstreamerRtspServer
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GObject

# Frame capture thread class
class FrameCaptureThread(threading.Thread):
    def __init__(self, rtsp_url, frame_queue, max_queue_size=30):
        threading.Thread.__init__(self)
        self.rtsp_url = rtsp_url
        self.frame_queue = frame_queue
        self.max_queue_size = max_queue_size
        self.stopped = False
        
    def run(self):
        cap = cv2.VideoCapture(self.rtsp_url)
        
        if not cap.isOpened():
            print(f"Error: Cannot open RTSP stream at {self.rtsp_url}")
            return
            
        print(f"Successfully connected to RTSP stream: {self.rtsp_url}")
        
        while not self.stopped:
            ret, frame = cap.read()
            if ret:
                # If queue is full, remove oldest frame
                if self.frame_queue.qsize() >= self.max_queue_size:
                    try:
                        self.frame_queue.get_nowait()
                    except queue.Empty:
                        pass
                
                
                self.frame_queue.put(frame)
            else:
                print("Failed to grab frame, attempting to reconnect...")
                cap.release()
                time.sleep(1)  # Wait before reconnecting
                cap = cv2.VideoCapture(self.rtsp_url)
                if not cap.isOpened():
                    print(f"Reconnection failed to {self.rtsp_url}")
                else:
                    print(f"Reconnected to {self.rtsp_url}")
        
        cap.release()
        
    def stop(self):
        self.stopped = True

# Sensor Factory class which inherits the GstRtspServer base class and add
# properties to it.
class SensorFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, frame_queue, **properties):
        super(SensorFactory, self).__init__(**properties)
        self.frame_queue = frame_queue
        self.number_frames = 0
        self.fps = 30
        self.duration = 1 / self.fps * Gst.SECOND  # duration of a frame in nanoseconds
        self.launch_string = 'appsrc name=source is-live=true block=true format=GST_FORMAT_TIME ' \
                             'caps=video/x-raw,format=BGR,width={},height={},framerate={}/1 ' \
                             '! videoconvert ! video/x-raw,format=I420 ' \
                             '! x264enc speed-preset=ultrafast tune=zerolatency ' \
                             '! rtph264pay config-interval=1 name=pay0 pt=96' \
                             .format(1920, 1080, self.fps)
    
    # method to get frames from the queue and push to the streaming buffer
    def on_need_data(self, src, length):
        try:
            # Non-blocking get with timeout
            frame = self.frame_queue.get(timeout=0.1)
            
            data = frame.tostring()
            buf = Gst.Buffer.new_allocate(None, len(data), None)
            buf.fill(0, data)
            buf.duration = self.duration
            timestamp = self.number_frames * self.duration
            buf.pts = buf.dts = int(timestamp)
            buf.offset = timestamp
            self.number_frames += 1
            retval = src.emit('push-buffer', buf)
            
            if self.number_frames % 30 == 0:  # Print every 30 frames to reduce console spam
                print('pushed buffer, frame {}, duration {} ns, durations {} s'.format(
                    self.number_frames, self.duration, self.duration / Gst.SECOND))
                
            if retval != Gst.FlowReturn.OK:
                print(retval)
                
        except queue.Empty:
            # If queue is empty, we can either skip this frame or use a placeholder
            print("Frame queue empty, skipping frame")
    
    # attach the launch string to the override method
    def do_create_element(self, url):
        return Gst.parse_launch(self.launch_string)
    
    # attaching the source element to the rtsp media
    def do_configure(self, rtsp_media):
        self.number_frames = 0
        appsrc = rtsp_media.get_element().get_child_by_name('source')
        appsrc.connect('need-data', self.on_need_data)

# Rtsp server implementation where we attach the factory sensor with the stream uri
class GstServer(GstRtspServer.RTSPServer):
    def __init__(self, frame_queue, **properties):
        super(GstServer, self).__init__(**properties)
        self.factory = SensorFactory(frame_queue)
        self.factory.set_shared(True)
        self.set_address("192.168.0.208")
        self.set_service(str(opt.port))
        self.get_mount_points().add_factory(opt.stream_uri, self.factory)
        self.attach(None)

# getting the required information from the user 
parser = argparse.ArgumentParser()
parser.add_argument("--port", default=8554, help="port to stream video", type=int)
parser.add_argument("--stream_uri", default="/stream", help="rtsp video stream uri")
parser.add_argument("--rtsp_source", default="rtsp://admin:admin@192.168.1.30/stream1", 
                    help="source rtsp stream url")
opt = parser.parse_args()

# initializing the threads and running the stream on loop.
GObject.threads_init()
Gst.init(None)

# Create a queue to hold frames between the capture thread and RTSP server
frame_queue = queue.Queue(maxsize=30)  # 1 seconds buffer at 30fps

# Start the frame capture thread
capture_thread = FrameCaptureThread(opt.rtsp_source, frame_queue)
capture_thread.daemon = True  # Thread will close when main program exits
capture_thread.start()

# Start the RTSP server
server = GstServer(frame_queue)

try:
    # Run the main loop
    loop = GObject.MainLoop()
    loop.run()
except KeyboardInterrupt:
    # Handle clean shutdown
    print("Stopping capture thread...")
    capture_thread.stop()
    capture_thread.join(timeout=1.0)
    print("Exiting...")
