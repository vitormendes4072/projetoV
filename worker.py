import os
from redis import Redis
from rq import Worker, Queue
from app import create_app

app = create_app()

with app.app_context():
    redis_url = app.config.get("REDIS_URL", "redis://localhost:6379/0")
    conn = Redis.from_url(redis_url)
    queues = [Queue("amazon-sync", connection=conn)]
    w = Worker(queues, connection=conn)
    w.work()
