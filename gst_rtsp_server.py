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
import numpy as np

# import required library like Gstreamer and GstreamerRtspServer
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GObject

class Video_Buffer:
    def __init__(self, pipe="video1", appsink_name="video_sink"):
        self._frame = None
        self.video_source = f'rtspsrc location={pipe} latency=10'

        self.video_codec = '! rtph264depay ! h264parse '  # 'application/x-rtp' 생략
        # self.video_decode = f' ! videoscale ! video/x-raw,width=1920,height=1080 ! videoconvert ! video/x-raw,format=(string)BGR ! appsink name={appsink_name} emit-signals=true sync=false max-buffers=3 drop=true'
        self.video_decode = f'! avdec_h264 ! videoscale ! video/x-raw,width=1920,height=1080 ! videoconvert ! video/x-raw,format=(string)BGR ! appsink name={appsink_name} emit-signals=true sync=false max-buffers=3 drop=true'

        self.video_pipe = None
        self.video_sink = None
        self.appsink_name = appsink_name
        self.run()

    def start_gst(self, config=None):
        if not config:
            config = [
                'videotestsrc ! decodebin',
                '! videoconvert ! video/x-raw,format=(string)BGR ! appsink name={self.appsink_name}'
            ]

        command = ' '.join(config)
        self.video_pipe = Gst.parse_launch(command)
        self.video_pipe.set_state(Gst.State.PLAYING)
        self.video_sink = self.video_pipe.get_by_name(self.appsink_name)
        
        if not self.video_sink:
            print(f"Failed to get appsink named {self.appsink_name}")
            return
        
        self.video_sink.set_property("emit-signals", True)
        self.video_sink.set_property("sync", False)

    @staticmethod
    def gst_to_opencv(sample):
        buf = sample.get_buffer()
        caps = sample.get_caps()
        array = np.ndarray(
            (
                caps.get_structure(0).get_value('height'),
                caps.get_structure(0).get_value('width'),
                3
            ),
            buffer=buf.extract_dup(0, buf.get_size()), dtype=np.uint8)
        return array

    def read(self):
        return self._frame is not None, self._frame

    def isOpened(self):
        return self._frame is not None

    def run(self):
        self.start_gst(
            [
                self.video_source,
                self.video_codec,
                # ' ! queue leaky=downstream max-size-buffers=10 ',
                self.video_decode
            ]
        )
        if self.video_sink:
            self.video_sink.connect('new-sample', self.callback)

        bus = self.video_pipe.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_message)

    def on_message(self, bus, message):
        t = message.type
        if t == Gst.MessageType.ERROR or t == Gst.MessageType.EOS:
            self.video_pipe.set_state(Gst.State.NULL)
            self.run()

    def callback(self, sink):
        sample = sink.emit('pull-sample')
        new_frame = self.gst_to_opencv(sample)
        self._frame = new_frame

        return Gst.FlowReturn.OK

    def release(self):
        self.video_pipe.set_state(Gst.State.NULL)

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

if __name__ == "__main__":
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

    max_queue_size = 30

    # Create a queue to hold frames between the capture thread and RTSP server
    frame_queue = queue.Queue(maxsize=max_queue_size)  # 1 seconds buffer at 30fps
    video_buffer = Video_Buffer(pipe=opt.rtsp_source)

    # Start the RTSP server
    server = GstServer(frame_queue)

    main_context = GObject.MainContext.default()
    main_loop = GObject.MainLoop.new(main_context, False)

    while True:
        ret, frame = video_buffer.read()
        if ret:
            if frame_queue.qsize() >= max_queue_size:
                try:
                    frame_queue.get_nowait()
                except queue.Empty:
                    pass

            frame = cv2.rotate(frame, cv2.ROTATE_180)

            frame_queue.put(frame)

            # cv2.imshow("test", frame)
            # cv2.waitKey(1)

        else:
            print("Disconnect RTSP")
            
         # GObject 주기 실행
        while main_context.pending():
            main_context.iteration(False)

        # 잠시 대기
    
     # 서버 종료
    server.stop()
    main_loop.quit()