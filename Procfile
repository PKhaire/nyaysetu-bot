release: python -m alembic -c alembic.ini upgrade head
web: gunicorn --config gunicorn.conf.py app:app
