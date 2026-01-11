# Changelog

All notable changes to this project will be documented in this file.

---

## [2.0.0] - 2026-01-11

### Added

**Data Structure**
- Two-table architecture: main observations layer + separate photos table
- One-to-many relationship between observations and photos
- Multiple photos per observation now properly supported
- Photo URLs stored in dedicated related table instead of single field
- Cleaner attribute table with improved data organization

**Taxonomy Database System**
- Local taxonomy database (1.4 million taxa from iNaturalist)
- Database Manager interface for installation and updates
- Three-tier system: local database, persistent cache, API fallback
- Significant performance improvement for taxonomy enrichment

**User Interface**
- Photo viewer for observation images
- Three date filtering modes: exact date, date range, month-specific
- Improved input validation
- Progress indicators for long operations

**Other**
- Bilingual interface (French/English)
- Context-sensitive help

### Fixed

- QGIS crash during large imports
- API authentication issues
- Symbology compatibility across different systems
- Memory management for large datasets
- Resource cleanup issues

### Changed

- Refactored code architecture for better maintainability
- Streamlined user workflow
- Updated documentation

### Technical

- QGIS 3.40+ (tested on 3.40 Bratislava)
- Python 3.12
- Requires pyinaturalist library

### Acknowledgments

Special thanks to Perplexity AI for assistance with debugging, and to the iNaturalist community for the taxonomy data.

---

## [1.0.2] - 2024-11-XX

### Fixed
- Minor bug fixes
- Improved error messages

---

## [1.0.1] - 2024-XX-XX

### Fixed
- Installation issues
- Documentation corrections

---

## [1.0.0] - 2024-XX-XX

### Initial Release

**Features**
- Import iNaturalist observations by circular area selection
- Input filtering (date, observer, taxon, quality grade)
- Output field selection
- GeoPackage export
- 7-level taxonomy enrichment (kingdom to species)

**Technical**
- QGIS 3.40+ compatibility
- Python 3.12
- Requires pyinaturalist library

---

For detailed information, see the [GitHub repository](https://github.com/yd73/iNaturalist_Import).
