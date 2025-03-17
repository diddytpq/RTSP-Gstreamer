import gi
import time, threading
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GObject, GLib

Gst.init(None)

import numpy as np
import cv2
from ultralytics import YOLO

class Video_Buffer():
    def __init__(self, url, appsink_name="server1"):
        self._frame = None
        # 입력 RTSP 스트림 URL (필요시 수정)
        self.video_source = f'rtspsrc location={url} latency=100'
        self.video_codec = '! application/x-rtp, encoding-name=(string)H264, payload=96 ! rtph264depay ! h264parse'
        self.video_decode = '! decodebin ! videoconvert ! video/x-raw,format=(string)BGR ! videoconvert'
        self.video_sink_conf = f'! appsink name={appsink_name} emit-signals=true sync=false '

        self.video_pipe = None
        self.video_sink = None
        self.appsink_name = appsink_name

        self.run()

    def start_gst(self, config=None):
        if not config:
            config = [
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
            self.start_gst([
                self.video_source,
                self.video_codec,
                self.video_decode,
                self.video_sink_conf
            ])
            self.video_sink.connect('new-sample', self.callback)
            bus = self.video_pipe.get_bus()
            bus.add_signal_watch()
            bus.connect("message", self.on_message)
        except Exception as e:
            print(e)

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

    def get_pipeline_state(self):
        state = self.video_pipe.get_state(1 * Gst.SECOND)
        return state.state.value_nick
    

# ------------------------
# RTSP 출력 송신 클래스
# ------------------------
class CustomFactory(GstRtspServer.RTSPMediaFactory):
    def __init__(self, width=640, height=480, framerate=30):
        super(CustomFactory, self).__init__()
        self.width = width
        self.height = height
        self.framerate = framerate
        # appsrc로 입력받은 BGR 영상을 videoconvert, 인코딩, RTP 패이로드로 변환하는 파이프라인
        self.launch_string = (
            "appsrc name=source is-live=true block=true format=time "
            f"caps=video/x-raw,format=BGR,width={width},height={height},framerate={framerate}/1 "
            "! videoconvert "
            "! video/x-raw,format=I420 "
            "! x264enc speed-preset=medium tune=zerolatency bitrate=2400 "
            "! rtph264pay name=pay0 pt=96 config-interval=1"
        )
        self.appsrc = None
        print("[CustomFactory] Initialized with launch string:")
        print(self.launch_string)

    def do_create_element(self, url):
        print("[CustomFactory] do_create_element called.")
        return Gst.parse_launch(self.launch_string)

def on_media_configure(factory, media):
    print("[on_media_configure] media-configure signal received.")
    element = media.get_element()
    appsrc = element.get_child_by_name("source")
    if appsrc is None:
        print("[on_media_configure] Could not retrieve appsrc element.")
    else:
        print("[on_media_configure] appsrc initialized:", appsrc)
    factory.appsrc = appsrc

class GstServer:
    def __init__(self, mount_point="/stream", width=640, height=480, framerate=30):
        self.mount_point = mount_point
        self.server = GstRtspServer.RTSPServer()
        self.factory = CustomFactory(width, height, framerate)
        self.factory.set_shared(True)
        self.factory.connect("media-configure", on_media_configure)
        self.server.get_mount_points().add_factory(self.mount_point, self.factory)
        self.loop = None
        self.timestamp = 0
        self.framerate = framerate
        self.frame_duration = Gst.util_uint64_scale_int(1, Gst.SECOND, self.framerate)

    def run(self):
        self.server.attach(None)
        self.loop = GLib.MainLoop()
        print("[GstServer] RTSP server running at rtsp://localhost:8554" + self.mount_point)
        self.loop.run()

    def push_frame(self, frame):
        if self.factory.appsrc is None:
            print("[push_frame] appsrc not initialized yet.")
            return
        data = frame.tobytes()
        buf = Gst.Buffer.new_allocate(None, len(data), None)
        buf.fill(0, data)
        buf.duration = self.frame_duration
        buf.pts = self.timestamp
        buf.dts = self.timestamp
        self.timestamp += self.frame_duration
        retval = self.factory.appsrc.emit("push-buffer", buf)
        if retval != Gst.FlowReturn.OK:
            print("[push_frame] Error pushing buffer:", retval)


# ------------------------
# 메인 처리 루프
# ------------------------
if __name__ == '__main__':
    yolo = YOLO('yolov8n.pt')

    # 카메라 접속 url
    rtsp=""

    # RTSP 입력 스트림 수신
    video_buffer = Video_Buffer()

    # RTSP 송신 서버 시작 (출력 스트림: 처리된 영상)
    gst_server = GstServer("/stream", width=1920, height=1080, framerate=30)
    server_thread = threading.Thread(target=gst_server.run, daemon=True)
    server_thread.start()

    # 송신 파이프라인(appsrc)이 초기화될 때까지 대기 (클라이언트가 PLAY 명령을 보내야 초기화됨)
    print("RTSP 출력 appsrc 초기화를 기다리는 중...")
    print("클라이언트(VLC, FFplay 등)로 rtsp://localhost:8554/stream 에 접속 후 PLAY를 눌러주세요.")
    while gst_server.factory.appsrc is None:
        time.sleep(0.1)

    while True:
        if video_buffer.frame_available():
            # 입력 프레임 수신
            frame = video_buffer.get_frame()
            # 이미지 처리 (사용자 정의)
            results = yolo(frame, imgsz=640, verbose=False)[0]
            processed_frame = results.plot()
            # 처리된 프레임을 RTSP 송신 서버로 전달
            gst_server.push_frame(processed_frame)
            # 테스트를 위해 로컬에서 처리된 영상 표시 (원하지 않으면 제거 가능)
            # cv2.imshow("Processed Frame", processed_frame)
            if cv2.waitKey(1) & 0xFF == 27:
                break

    cv2.destroyAllWindows()