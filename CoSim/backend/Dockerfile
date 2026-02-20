FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on

WORKDIR /app

# Install system dependencies including OpenGL/EGL for headless MuJoCo rendering
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        ffmpeg \
        libopus0 \
        libgl1-mesa-dev \
        libgl1 \
        libglew-dev \
        libosmesa6-dev \
        libglfw3 \
        libglfw3-dev \
        gdb \
        gdbserver \
        lldb \
        patchelf \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables for headless rendering (use EGL instead of GLFW)
ENV MUJOCO_GL=egl \
    PYOPENGL_PLATFORM=egl

COPY pyproject.toml README.md ./
COPY src ./src
COPY templates ./templates
COPY alembic ./alembic
COPY alembic.ini ./
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

RUN pip install --upgrade pip \
    && pip install --no-cache-dir .

EXPOSE 8000

ENTRYPOINT ["docker-entrypoint.sh"]
