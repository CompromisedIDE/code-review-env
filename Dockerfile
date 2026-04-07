FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Verify tasks load at build time — fails build if any import is broken
RUN python -c "\
from code_review_env.tasks import REGISTRY; \
tasks = REGISTRY.list_tasks(); \
assert len(tasks) == 3, f'Expected 3 tasks got {len(tasks)}'; \
print(f'Build check: {len(tasks)} tasks loaded OK') \
"

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=10s \
  --start-period=10s --retries=3 \
  CMD python -c "\
import urllib.request, sys; \
r = urllib.request.urlopen('http://localhost:7860/health', timeout=5); \
sys.exit(0 if r.status == 200 else 1)"

CMD ["uvicorn", "server.app:app", \
  "--host", "0.0.0.0", \
  "--port", "7860", \
  "--log-level", "info"]
