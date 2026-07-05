class PositionManager:
    def load_all(self):
        return [{"id": 1, "code": "2330", "name": "台積電", "entry": 600, "shares": 10}]
    
    def risk_summary(self, positions, total_capital):
        return {"total_positions": len(positions), "capital": total_capital}
    
    def create(self, data):
        return {"id": 2, **data}
    
    def update(self, pid, data):
        return {"id": pid, **data}
    
    def delete(self, pid):
        return True
