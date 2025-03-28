

import numpy as np

import gi

gi.require_version('Gst', '1.0')
from gi.repository import Gst
Gst.init(None)

class Video_Buffer:
    def __init__(self, pipe="video1", appsink_name="video_sink"):
        self._frame = None
        # self.video_source = f'rtspsrc location=rtsp://{pipe} latency=10 buffer-mode=0 protocols=tcp'
        self.video_source = f'rtspsrc location=rtsp://{pipe} latency=10'

        # self.video_codec = '! application/x-rtp, encoding-name=(string)H264, payload=96 ! rtph264depay ! h264parse '
        self.video_codec = '! rtph264depay ! h264parse '  # 'application/x-rtp' 생략
        # self.video_codec = '! application/x-rtp, encoding-name=(string)H264, payload=96 ! rtph264depay ! h264parse '
        # self.video_decode = f'! decodebin ! videoscale ! video/x-raw,width=640,height=480 ! videoconvert ! video/x-raw,format=(string)BGR ! appsink name={appsink_name} emit-signals=true sync=false max-buffers=3 drop=true'
        self.video_decode = f'! decodebin ! videoscale ! video/x-raw,width=1920,height=1080 ! videoconvert ! video/x-raw,format=(string)BGR ! appsink name={appsink_name} emit-signals=true sync=false max-buffers=3 drop=true'
        
        # self.video_decode = f'! decodebin ! videoconvert ! appsink name={appsink_name} emit-signals=true sync=false max-buffers=10 drop=true'
        
        # self.video_decode = f'! decodebin ! videorate ! video/x-raw,framerate=30/1,format=(string)BGR ! videoconvert ! appsink name={appsink_name} emit-signals=true sync=false max-buffers=3 drop=true'
        
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

    def get_frame(self):
        return self._frame

    def frame_available(self):
        return self._frame is not None

    def run(self):
        try:
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
        except Exception as e:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            tb = traceback.format_exc()
            print(f"Error occurred at {current_time}: {e}\n{tb}", file=sys.stderr)

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
        self.video_pipe.set_state(Gst.State.NULL)

if __name__ == '__main__':
    import time
    # pipe = "admin:1234@117.17.159.143/normal1"
    # pipe = "admin:1234@117.17.159.143/normal1"
    pipe = '192.168.0.208/stream'


    video = Video_Buffer(pipe = pipe)

    time.sleep(1)
    import cv2
    cv2.namedWindow("test")

    while True:
        print(video.frame_available())
        if video.frame_available():
            frames = video.get_frame()

            cv2.imshow('test', frames)

            if cv2.waitKey(1) & 0xFF == 27:
                break
        
    cv2.destroyAllWindows()






