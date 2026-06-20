from typing import List, Dict
import numpy as np
from datetime import datetime

def predict_future_score(historical_scores: List[float]) -> float:
    """
    Simple linear regression to predict the next score based on trends.
    """
    if len(historical_scores) < 2:
        return historical_scores[0] if historical_scores else 0.0
    
    # x = [0, 1, 2, ...] (time steps)
    # y = scores
    x = np.arange(len(historical_scores))
    y = np.array(historical_scores)
    
    # Slope (m) and Intercept (c)
    m, c = np.polyfit(x, y, 1)
    
    # Predict next step (current length)
    prediction = m * len(historical_scores) + c
    
    # Clamp to [0, 100]
    return float(np.clip(prediction, 0, 100))

def generate_student_forecast(student_results: List[Dict]) -> Dict:
    """
    Aggregates historical data and generates a forecast.
    """
    if not student_results:
        return {"forecast": 0.0, "trend": "stable"}
    
    # Sort by academic context (simplified: assuming chronological order of results)
    # In a real app, we'd sort by term/year
    scores = [r["score"] for r in student_results]
    
    forecasted_mean = predict_future_score(scores)
    current_mean = sum(scores) / len(scores)
    
    trend = "improving" if forecasted_mean > current_mean + 2 else \
            "declining" if forecasted_mean < current_mean - 2 else "stable"
            
    return {
        "current_mean": round(current_mean, 1),
        "forecasted_mean": round(forecasted_mean, 1),
        "trend": trend,
        "historical_data": scores
    }
