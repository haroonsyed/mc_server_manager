docker build --pull -t mc-server-manager .
docker save mc-server-manager | sudo k3s ctr images import -