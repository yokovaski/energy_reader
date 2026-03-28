class ReadHandlerInterface:
    def handle_read(self, data: dict) -> None:
        pass

    def get_name(self) -> str:
        pass
    
    def seconds_since_last_run_time(self) -> float:
        pass
