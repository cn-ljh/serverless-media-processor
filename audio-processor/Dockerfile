FROM public.ecr.aws/lambda/python:3.9

# Set up working directory
WORKDIR /var/task

# Install required tools
RUN yum install -y tar xz wget

# Upgrade pip
RUN pip install --upgrade pip

# Download and extract FFmpeg binaries
RUN mkdir -p /var/task/ffmpeg && \
    cd /var/task/ffmpeg && \
    wget https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz && \
    tar -xvf ffmpeg-release-amd64-static.tar.xz && \
    mv ffmpeg-*-amd64-static/* . && \
    rm -rf ffmpeg-*-amd64-static && \
    rm ffmpeg-release-amd64-static.tar.xz

# Add ffmpeg to PATH
ENV PATH="/var/task/ffmpeg:${PATH}"

# Ensure all binaries have execute permissions
RUN chmod -R +x /var/task/ffmpeg

# Copy function code and install dependencies
COPY . ${LAMBDA_TASK_ROOT}

# Install Python dependencies
RUN pip install -r requirements.txt -t /var/task

# Set the CMD to your handler
CMD [ "handler.lambda_handler" ]
