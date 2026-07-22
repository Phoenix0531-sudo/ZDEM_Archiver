# ZDEM Archiver

**Policy-friendly archive and cleanup helpers for bulky ZDEM simulation dumps.**

[English](README.md) | [中文](README.zh-CN.md)

[![CI](https://github.com/Phoenix0531-sudo/ZDEM_Archiver/actions/workflows/ci.yml/badge.svg)](https://github.com/Phoenix0531-sudo/ZDEM_Archiver/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Long DEM campaigns fill disks with raw frames. This utility helps **classify keep vs reclaimable** data and run archive/purge flows with dry-run discipline — not a blind `rm -rf`.

## Preview

![ZDEM Archiver](docs/screenshots/preview.png)

## Install / run

```bash
git clone https://github.com/Phoenix0531-sudo/ZDEM_Archiver.git
cd ZDEM_Archiver
pip install -r requirements.txt
# project entry modules — always dry-run on precious campaigns first
pytest tests/
```

## License

MIT. See [LICENSE](LICENSE).
