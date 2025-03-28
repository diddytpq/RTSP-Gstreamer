import cv2
    
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstApp', '1.0')
from gi.repository import Gst, GstApp, GLib

import numpy as np

Gst.init(None)


def on_new_sample(sink):
    sample = sink.emit("pull-sample")
    if sample:
        buf = sample.get_buffer()
        caps = sample.get_caps()
        
        width = caps.get_structure(0).get_value("width")
        height = caps.get_structure(0).get_value("height")
        
        _, map_info = buf.map(Gst.MapFlags.READ)
        frame = np.ndarray(
            (height, width, 3),
            buffer=map_info.data,
            dtype=np.uint8
        )
        buf.unmap(map_info)
        
        # OpenCV로 프레임 처리
        cv2.imshow("RTSP Stream", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            return Gst.FlowReturn.EOS
        
    return Gst.FlowReturn.OK

# RTSP 스트림 URL 설정
rtsp_url = "rtsp://admin:admin@192.168.1.30/stream1"

# GStreamer 파이프라인 생성
pipeline_str = f"""
    rtspsrc location={rtsp_url} latency=0 ! 
    rtph264depay ! h264parse ! avdec_h264 ! 
    videoconvert ! video/x-raw,format=BGR ! 
    appsink name=sink emit-signals=True
"""

pipeline = Gst.parse_launch(pipeline_str)
sink = pipeline.get_by_name("sink")
sink.connect("new-sample", on_new_sample)

# 파이프라인 시작
pipeline.set_state(Gst.State.PLAYING)

# GLib 메인 루프 실행
loop = GLib.MainLoop()
try:
    loop.run()
except KeyboardInterrupt:
    pass

# 정리
pipeline.set_state(Gst.State.NULL)
cv2.destroyAllWindows()
