docker build -t mc-server-manager .
docker save mc-server-manager | sudo k3s ctr images import -