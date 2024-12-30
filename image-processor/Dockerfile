FROM public.ecr.aws/lambda/python:3.9

# Install system dependencies required for Pillow, OpenCV, and blind-watermark
RUN yum update -y && \
    yum install -y \
    gcc \
    python3-devel \
    libjpeg-devel \
    zlib-devel \
    mesa-libGL \
    mesa-libGLU \
    atlas-devel \
    lapack-devel \
    blas-devel \
    && yum clean all

# Create required symlinks for OpenCV
RUN ln -s /usr/lib64/libGL.so.1 /usr/lib/libGL.so && \
    ln -s /usr/lib64/libGLU.so.1 /usr/lib/libGLU.so

# Copy requirements file
COPY requirements.txt ${LAMBDA_TASK_ROOT}

# Install Python dependencies
RUN pip install -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Copy function code
COPY . ${LAMBDA_TASK_ROOT}/

# Set the CMD to your handler
CMD [ "handler.handler" ]
