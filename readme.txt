1. Create droplet from Ubuntu GNOME
2. Wait for 5 mins - than - Launch Droplet Console 
3. Find User and VNC Password
4. connect via vnc viewer
5. Login with user - and given password.
6. Search "display" make resolution 1792x1344
7. RUN Now : apt install python3-pip
8. Type Manually - 

git clone https://github.com/domain-metrics/lion.git 

9. Get data from readme - cat readme.txt

python3 -m camoufox fetch
curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up --authkey=tskey-auth-kFattZED7w11CNTRL-jpUv2dnKwZcz2qxjsWYcacPTdVnia5upg
python3 server.py
