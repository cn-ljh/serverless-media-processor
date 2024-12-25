#!/bin/bash

# Create a directory for the layer
mkdir -p lambda-layer/ffmpeg/bin

# Download and extract static ffmpeg build
curl -O https://johnvansickle.com/ffmpeg/builds/ffmpeg-git-amd64-static.tar.xz
tar xf ffmpeg-git-amd64-static.tar.xz
mv ffmpeg-git-*/ffmpeg lambda-layer/ffmpeg/bin/
mv ffmpeg-git-*/ffprobe lambda-layer/ffmpeg/bin/

# Clean up
rm -rf ffmpeg-git-* ffmpeg-git-amd64-static.tar.xz

# Create layer zip
cd lambda-layer
zip -r ../ffmpeg-layer.zip *
cd ..

# Clean up layer directory
rm -rf lambda-layer
