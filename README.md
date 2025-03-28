# RTSP-Gstreamer


## RockChip RK3588 ubuntu 24.04
```bash
sudo apt install python3-pip
sudo apt-get install gstreamer1.0-libav

sudo apt install libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev libgstrtspserver-1.0-dev libopencv-dev pkg-config build-essential

sudo apt-get install gstreamer1.0-plugins-bad gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-ugly gstreamer1.0-tools libgstreamer1.0-dev libgstreamer1.0-0 libgstreamer-plugins-base1.0-dev gtk-doc-tools python-gi-dev gir1.2-gst-rtsp-server-1.0


python3 -m pip config set global.break-system-packages true
pip3 install numpy opencv-python



```


# 8554 port를 554로 맵핑
```
sudo iptables -t nat -A PREROUTING -p tcp --dport 554 -j REDIRECT --to-port 8554
sudo iptables -t nat -A PREROUTING -p udp --dport 554 -j REDIRECT --to-port 8554

#영구적인 포트 포워딩 설정 (재부팅 후에도 유지):
bash
sudo apt-get install iptables-persistent
# 설치 중에 현재 규칙을 저장할지 물어보면 '예'를 선택
```