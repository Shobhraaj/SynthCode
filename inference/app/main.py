from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from inference.app.config import get_settings
from inference.app.model_loader import ModelLoader
from inference.app.predictor import Predictor
from inference.app.schemas import PredictRequest, PredictResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    loader = ModelLoader(settings.MODEL_PATH, settings.MODEL_DEVICE)
    predictor = Predictor(loader.model, loader.tokenizer, settings)
    if settings.WARMUP_ON_STARTUP:
        predictor.warmup()
    app.state.predictor = predictor
    yield
    app.state.predictor = None


app = FastAPI(title="SynthCode Inference", version="1.0.0", lifespan=lifespan)


@app.post("/predict/batch", response_model=PredictResponse)
async def predict_batch(request: PredictRequest) -> PredictResponse:
    return app.state.predictor.predict_batch(request.files)


@app.get("/health")
async def health() -> dict[str, bool | str]:
    try:
        import torch

        gpu_available = torch.cuda.is_available()
    except ImportError:
        gpu_available = False
    return {"status": "ok", "gpu": gpu_available}

