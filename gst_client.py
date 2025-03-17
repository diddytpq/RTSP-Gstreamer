import numpy as np

import gi

gi.require_version('Gst', '1.0')
from gi.repository import Gst



class Video_Buffer():
    def __init__(self, camera_name = "video1", appsink_name = "camera1"):
        Gst.init(None)

        self._frame = None
        self.video_source = 'rtspsrc location=rtsp://127.0.0.1:8554/stream latency=10'

        self.video_codec = '! application/x-rtp, encoding-name=(string)H264, payload=96 ! rtph264depay ! h264parse '
        self.video_decode =  '! decodebin ! videoconvert ! video/x-raw,format=(string)BGR ! videoconvert'
        # Create a sink to get data
        self.video_sink_conf = f'! appsink name={appsink_name} emit-signals=true sync=false max-buffers=10 drop=true'
        print(self.video_source)

        self.video_pipe = None
        self.video_sink = None
        self.appsink_name = appsink_name

        self.run()

    def start_gst(self, config=None):
        if not config:
            config = \
                [
                    'videotestsrc ! decodebin',
                    '! videoconvert ! video/x-raw,format=(string)BGR ! videoconvert',
                    '! appsink'
                ]

        command = ' '.join(config)
        self.video_pipe = Gst.parse_launch(command)
        self.video_pipe.set_state(Gst.State.PLAYING)
        self.video_sink = self.video_pipe.get_by_name(self.appsink_name)

    @staticmethod
    def gst_to_opencv(sample):
        """Transform byte array into np array
        Args:
            sample (TYPE): Description
        Returns:
            TYPE: Description
        """
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

    def get_frame(self):
        """ Get Frame
        Returns:
            iterable: bool and image frame, cap.read() output
        """
        # self._frame = cv2.resize(self._frame, (640,480))
        return self._frame

    def frame_available(self):
        """Check if frame is available
        Returns:
            bool: true if frame is available
        """
        return type(self._frame) != type(None)

    def run(self):
        try:
            """ Get frame to update _frame
            """

            self.start_gst(
                [
                    self.video_source,
                    self.video_codec,
                    self.video_decode,
                    self.video_sink_conf
                ])

            self.video_sink.connect('new-sample', self.callback)

            bus = self.video_pipe.get_bus()
            bus.add_signal_watch()
            bus.connect("message", self.on_message)
        except Exception as e :
            print(e)
            pass

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
    
    def stop(self):
        """Stop the pipeline"""
        self.video_pipe.set_state(Gst.State.NULL)

    def get_pipeline_state(self):
        state = self.video_pipe.get_state(1 * Gst.SECOND)
        return state.state.value_nick
    
if __name__ == '__main__':
    import time

    video = Video_Buffer()

    time.sleep(1)
    import cv2

    while True:
        if video.frame_available():
            frames = video.get_frame()


            cv2.imshow('Combined Frame', frames)

            if cv2.waitKey(1) & 0xFF == 27:
                break

    cv2.destroyAllWindows()