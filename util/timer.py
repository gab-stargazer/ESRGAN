import time

class Stopwatch:
    def __init__(self):
        self.start_time = None
        self.end_time = None

    def start(self):
        if self.start_time is None:
            self.start_time = time.time()

    def stop(self):
        if self.start_time is not None and self.end_time is None:
            self.end_time = time.time()

    def get_elapsed_time(self):
        if self.start_time is not None and self.end_time is None:
            elapsed_time = time.time() - self.start_time
            return elapsed_time
        elif self.end_time is not None:
            return f'{self.end_time - self.start_time:.2f}'
        else:
            return 0

    def run(self):
        while True:
            command = input().lower()
            if command == 's':
                self.stop()
                break
            elif command == 't':
                elapsed_time = self.get_elapsed_time()
                print(f"Elapsed Time: {elapsed_time:.2f} seconds")
            elif command == 'r':
                self.reset()
            else:
                self.start()

    def reset(self):
        if self.start_time is not None or self.end_time is not None:
            self.start_time = None
            self.end_time = None
            print("Stopwatch has been reset.")
        else:
            print("Stopwatch hasn't started yet.")