 FROM python:3.11-slim
 
 ENV PYTHONDONTWRITEBYTECODE=1
 ENV PYTHONUNBUFFERED=1
 
 WORKDIR /workspace
 
RUN pip install --no-cache-dir uv
RUN uv pip install --system fastapi "pydantic>=2.6" "uvicorn[standard]>=0.27" "tzdata>=2024.1"
 
COPY . /workspace/
 
 EXPOSE 7860
 
 CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
