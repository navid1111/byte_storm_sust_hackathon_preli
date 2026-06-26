<h1 align="center">FastAPI + Prometheus + Grafana :tada:</h1>

This is a minimal setup that you can build to monitor your FastAPI microservice.

## Installation

There are only two prerequisites:

* [Docker](https://docs.docker.com/get-docker/)
* [Docker-compose](https://docs.docker.com/compose/install/)

Having both, you'll need to clone the repository:

``` bash
git clone https://github.com/Kludex/fastapi-prometheus-grafana
```

## Usage

You'll need to run the docker containers:

``` bash
docker-compose up
```

Now you have access to those three containers and their respective ports:

* Prometheus: http://localhost:9090/
* Grafana: http://localhost:3000/
* FastAPI: http://localhost:8000/

On the FastAPI, you can access `/metrics` endpoint to see the data Prometheus is scraping from it.

## How it looks like

<p align="center">
  <img src="./dashboard.jpeg">
</p>

## References

* [Prometheus FastAPI Instrumentator](https://github.com/trallnag/prometheus-fastapi-instrumentator)
* [Generate and Track Metrics for Flask API Applications Using Prometheus and Grafana](https://medium.com/swlh/generate-and-track-metrics-for-flask-api-applications-using-prometheus-and-grafana-55ddd39866f0)
* [PromQL for Humans](https://timber.io/blog/promql-for-humans/)

## Testing

Unit tests live in `app/tests/` and run with `pytest`. They cover the `/` endpoint, the `/metrics` endpoint, and the CORS middleware.

### Run locally (host machine)

Requires Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r app/requirements.txt -r app/requirements-dev.txt
cd app && pytest
```

The test run includes coverage (`pytest-cov`) and fails if coverage drops below 100%.

### Run inside Docker

The dev dependencies are not baked into the app image to keep it small. Install them once into the running container, then run pytest:

```bash
docker compose exec app pip install -r requirements-dev.txt
docker compose exec app pytest
```

The `app/` directory is bind-mounted into the container (see `docker-compose.yaml`), so edits to test files and `pytest.ini` on the host are immediately visible inside the container.
