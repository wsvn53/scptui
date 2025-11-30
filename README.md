# SCPTUI - SCP Interactive Tool

📁 An interactive SCP (Secure Copy Protocol) tool with a beautiful terminal UI for easy file transfers between local and remote systems.

![SCPTUI Demo](screenshots/scptui-demo.png)

## Features

- 🎨 **Interactive Terminal UI** - Built with Textual and Rich for a modern CLI experience
- 📤 **Upload Files** - Select local files/folders and upload to remote server
- 📥 **Download Files** - Browse remote files and download to local system
- 📊 **Progress Tracking** - Real-time progress bars with tqdm integration
- 🔐 **Secure Connections** - SSH key and password authentication support
- 🚀 **Easy to Use** - Simple command-line interface

## Installation

```bash
# Clone the repository
cd scptui

# Install dependencies
pip install -e .

# Or install with development dependencies
pip install -e ".[dev]"
```

## Usage

SCPTUI uses the same syntax as the traditional SCP command:

```bash
scptui [-P port] [-i identity_file] [-r] [-v] [-R] source target
```

**Remote path format:** `user@host[:port]:path`
- Standard: `user@example.com:/path`
- With custom port: `user@example.com:2222:/path`

### Download files from remote server

```bash
# Download a file
scptui user@example.com:/remote/file.txt /local/path/

# Download a directory (recursive)
scptui -r user@example.com:/remote/dir/ /local/dir/
```

### Upload files to remote server

```bash
# Upload a file
scptui /local/file.txt user@example.com:/remote/path/

# Upload a directory (recursive)
scptui -r /local/dir/ user@example.com:/remote/path/
```

### Command options

```bash
scptui --help

positional arguments:
  source                Source file/directory (local path or user@host:path)
  target                Target file/directory (local path or user@host:path)

options:
  -h, --help            show this help message and exit
  -P port               Port to connect to on the remote host (default: 22)
  -i identity_file      Identity file (private key) for public key authentication
  -p PASSWORD           Password for authentication
  -r, --recursive       Recursively copy entire directories
  -v, --verbose         Verbose mode
  -R, --interactive-right
                        Browse local directory (reverse default behavior of browsing remote)
```

## Examples

### Using SSH key authentication

```bash
scptui -i ~/.ssh/id_rsa user@example.com:/remote/file.txt /local/
```

### Using password authentication

```bash
scptui -p mypassword user@example.com:/remote/file.txt /local/
```

### Custom SSH port

You can specify the port in two ways:

**Using -P flag:**
```bash
scptui -P 2222 user@example.com:/remote/file.txt /local/
```

**Inline in the path (user@host:port:path):**
```bash
scptui user@example.com:2222:/remote/file.txt /local/
```

**Note:** Port in path takes precedence over `-P` flag.

### Verbose mode with recursive copy

```bash
scptui -v -r -i ~/.ssh/id_rsa /local/dir/ user@example.com:/remote/backup/
```

### Combined example with custom port

```bash
scptui -i ~/.ssh/id_rsa -r /local/backup/ user@example.com:1234:/remote/backup/
```

### Interactive selection side

By default, the interactive file browser automatically opens on the **remote** (SSH) side:
- **Download**: Browse remote files interactively to select what to download
- **Upload**: Browse remote destination interactively to select where to upload

Use `-R` to switch to browsing the **local** directory:

```bash
# Upload: Browse local files interactively (select what to upload)
scptui -R /local/path/ user@example.com:/remote/path/

# Download: Browse local destination interactively (select where to save)
scptui -R user@example.com:/remote/path/ /local/path/
```

## Development

```bash
# Install development dependencies
pip install -e ".[dev]"

# Format code with black
black scptui/

# Lint with ruff
ruff check scptui/

# Run tests
pytest
```

## Dependencies

- **paramiko** - SSH/SCP functionality
- **rich** - Beautiful terminal output
- **textual** - Interactive terminal UI framework
- **tqdm** - Progress bars

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
