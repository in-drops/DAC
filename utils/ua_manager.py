import random
from pathlib import Path

# Обновлять при выходе новой стабильной версии Chrome
CHROME_VERSIONS = [145, 146, 147]

# Платформы для рандомизации отпечатков
PLATFORMS = [
    "Windows NT 10.0; Win64; x64",
    "Windows NT 11.0; Win64; x64",
    "X11; Linux x86_64",
    "X11; Ubuntu; Linux x86_64",
]

UA_FILE = Path(__file__).parent.parent / "config" / "data" / "user_agents.txt"


def _random_patch() -> str:
    """Случайный патч вида 1234.56"""
    return f"{random.randint(1000, 9999)}.{random.randint(10, 99)}"


def generate_user_agents(count: int = 100) -> list[str]:
    agents = []
    for _ in range(count):
        platform = random.choice(PLATFORMS)
        version  = random.choice(CHROME_VERSIONS)
        patch    = _random_patch()
        ua = (
            f"Mozilla/5.0 ({platform}) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{version}.0.{patch} Safari/537.36"
        )
        agents.append(ua)
    return agents


def update_ua_file():
    agents = generate_user_agents(100)
    UA_FILE.write_text("\n".join(agents), encoding="utf-8")
    print(f"user_agents.txt обновлён: {len(agents)} строк, версии Chrome: {CHROME_VERSIONS}")


def get_random_ua() -> str:
    lines = UA_FILE.read_text(encoding="utf-8").splitlines()
    return random.choice([line for line in lines if line.strip()])


if __name__ == "__main__":
    update_ua_file()
