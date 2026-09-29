"""CS/math vocabulary with canonical spelling, plus the names of your own local projects."""
import re
from pathlib import Path

TECH = """
GitHub GitLab Git VS Code Neovim NvChad LazyVim Obsidian Dataview TickTick Notion Figma Vercel Supabase PocketBase
Firebase Docker Kubernetes WSL PowerShell Bash Zsh Linux Ubuntu macOS iOS Android Windows Terminal
Python NumPy SciPy SymPy pandas Matplotlib PyTorch TensorFlow JAX scikit-learn Jupyter conda pip venv
FastAPI Flask Django Pydantic asyncio pytest mypy Ruff uv Poetry
JavaScript TypeScript Node.js npm pnpm Vite React Next.js Svelte Tailwind Chakra UI MUI Expo Deno Bun
C++ CMake OpenMP MPI CUDA cuDNN cuBLAS NVIDIA Jetson TensorRT ONNX LiteRT OpenGL Vulkan GLSL Unity Godot
Rust Cargo Go Haskell OCaml Lean Mathlib Coq Isabelle LaTeX Overleaf TikZ
SQL PostgreSQL SQLite MySQL Redis MongoDB GraphQL REST gRPC WebSocket OAuth JWT JSON YAML TOML
LLM LLMs RAG GraphRAG MCP Claude Claude Code Anthropic OpenAI ChatGPT Codex Gemini Ollama Qwen Llama Mistral
Whisper faster-whisper CTranslate2 Hugging Face transformers LoRA fine-tuning embeddings tokenizer
ROS ROS 2 Gazebo ArduPilot PX4 MAVLink CubeSat LAMMPS OVITO OpenSim
LeetCode Codeforces arXiv OEIS Erdős Hadwiger-Nelson Conway Shannon Hankel zeta irrationality
networkx pywebview pystray rapidfuzz wordfreq Tkinter PyInstaller Graphviz Mermaid regex API APIs SDK CLI GUI UI UX CI/CD DevOps backend frontend fullstack
"""

SLANG_WORDS = """deadass lowkey highkey bruh finna tryna rizz rizzler delulu sus yapping yapper glazing bussin ong istg
aura cooked mid based NPC ick situationship gyat skibidi sigma looksmaxxing mogging goated""".split()

# folder names too generic to be "your" vocabulary; remove anything else from the Dictionary page
GENERIC = {"models", "model", "stage", "schema", "portfolio", "website", "personal-website", "test", "tests", "demo",
           "example", "examples", "sandbox", "playground", "scripts", "notes", "src", "app", "my project"}


def tech_terms():
    multi = ["VS Code", "Claude Code", "Hugging Face", "ROS 2", "Chakra UI", "Windows Terminal", "Node.js", "Next.js"]
    rest = TECH
    for m in multi:
        rest = rest.replace(m, " ")
    return multi + [w for w in rest.split() if w]


def project_names(home=Path.home()):
    out = []
    try:
        for d in home.iterdir():
            if d.is_dir() and (d / ".git").exists() and d.name.lower() not in GENERIC:
                out.append(d.name)
    except OSError:
        pass
    return out


def seed(memory):
    for t in tech_terms():
        memory.add_term(t, "tech")
    for w in SLANG_WORDS:
        memory.add_term(w, "slang")
    for name in project_names():
        spoken = re.sub(r"[-_]+", " ", re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name))
        # only names Whisper wouldn't already spell right
        if memory.is_rare(spoken) or re.search(r"\d|[a-z][A-Z]", name):
            memory.add_term(name, "project", seen=40)
