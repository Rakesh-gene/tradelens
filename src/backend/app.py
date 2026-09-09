"""Small dependency-injected HTTP API for the TradeLens application."""

from server import HOST, PORT, build_repository, create_pipeline_scheduler, create_server
from auth import AuthService, RegistrationResult, UserRepository
from repositories import InMemoryUserRepository, PostgresUserRepository
from server_http import ApiHandler


def main() -> None:
    server = create_server()
    scheduler = create_pipeline_scheduler(server)
    if scheduler is not None:
        scheduler.start()
        print("Daily incremental all-equities pipeline scheduled for 19:00 Asia/Kolkata")
    print(f"TradeLens backend listening on http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping backend")
    finally:
        if scheduler is not None:
            scheduler.stop()
        server.server_close()


if __name__ == "__main__":
    main()
