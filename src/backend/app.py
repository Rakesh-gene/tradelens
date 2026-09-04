"""Small dependency-injected HTTP API for the TradeLens application."""

from server import HOST, PORT, build_repository, create_server
from auth import AuthService, RegistrationResult, UserRepository
from repositories import InMemoryUserRepository, PostgresUserRepository
from server_http import ApiHandler


def main() -> None:
    server = create_server()
    print(f"TradeLens backend listening on http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping backend")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
