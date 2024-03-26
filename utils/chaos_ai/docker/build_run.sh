cd ..
# bash cython_build.sh
# mv -v dist/aichaos*.whl docker
cd docker 
docker build -t aichaos:1.0 .
docker rm $(docker ps -q -f 'status=exited')
docker run --privileged -v /var/run/docker.sock:/var/run/docker.sock --name aichaos -p 5001:5001 aichaos:1.0
