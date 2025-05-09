FROM public.ecr.aws/lambda/python:3.9

# Install system dependencies
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
    xorg-x11-fonts-* \
    libSM.x86_64 \
    libXinerama-devel \
    binutils \
    tar \
    gzip \
    xz \
    openssl \
    nss-tools \
    dbus-libs \
    cups-libs \
    && yum clean all

# Copy Python dependencies file
COPY requirements.txt ${LAMBDA_TASK_ROOT}/

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install -r ${LAMBDA_TASK_ROOT}/requirements.txt

# Copy function code
COPY . ${LAMBDA_TASK_ROOT}

# Set the CMD to your handler
CMD [ "handler.handler" ]
