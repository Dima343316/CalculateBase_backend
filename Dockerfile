FROM python:3.10

ENV PYTHONUNBUFFERED=1

WORKDIR /web_django

COPY requirements.txt .


RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
