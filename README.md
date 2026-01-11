# iNaturalist Import

QGIS plugin for importing biodiversity observations from iNaturalist with spatial filtering and taxonomy enrichment.

---

## Overview

This plugin allows users to import iNaturalist biodiversity data into QGIS for spatial analysis and mapping. It provides tools for selecting geographic areas, filtering observations, and enriching data with complete taxonomic classification.

**Main features:**
- Two-layer output: observations + related photos table (one-to-many relationship)
- Circular area selection on the map
- Date, user, taxon, and quality filters
- Automatic taxonomy enrichment (7 levels: kingdom to species)
- Local taxonomy database for improved performance
- Bilingual interface (English/French)

---

## Version 2.0.0

This version introduces significant structural improvements with a two-table architecture that properly handles multiple photos per observation. It also includes a local taxonomy database system for improved performance, enhanced date filtering options, and better user interface.

See [CHANGELOG.md](CHANGELOG.md) for detailed changes.

---

## Installation

### Prerequisites

- QGIS 3.40 or higher (tested on QGIS 3.40)
- Python 3.12 (included with QGIS)
- Internet connection

### Step 1: Install the Plugin

**From QGIS Plugin Repository:**
1. Open QGIS
2. Go to Plugins → Manage and Install Plugins
3. Search for "iNaturalist Import"
4. Click Install Plugin

**From ZIP file:**
1. Download from [GitHub Releases](https://github.com/yd73/iNaturalist_Import/releases)
2. In QGIS: Plugins → Manage and Install Plugins → Install from ZIP
3. Select the downloaded file

### Step 2: Install Python Dependency

The plugin requires the `pyinaturalist` library.

**Windows:**
1. Close QGIS
2. Open OSGeo4W Shell
3. Run: `python -m pip install pyinaturalist`
4. Restart QGIS

**macOS/Linux:**
1. Close QGIS
2. Open Terminal
3. Run: `python3 -m pip install pyinaturalist`
4. Restart QGIS

If the library is missing, the plugin will display installation instructions on first use.

### Step 3: Download Taxonomy Database (Optional but Recommended)

1. In QGIS: Extensions → iNaturalist Import → Taxonomy Database Manager
2. Click "Download Database"
3. Wait for completion (approximately 5 seconds)

The local database improves taxonomy enrichment performance. Without it, the plugin uses the iNaturalist API directly (slower but functional).

---

## Usage

### Basic Workflow

1. **Launch the import tool**
   - Click the iNaturalist Import icon in the toolbar

2. **Define search area**
   - Click on the map to set center point
   - Enter radius in meters
   - The circular area will be displayed on the map

3. **Configure filters** (optional)
   - Date: specific date, date range, or month filter
   - User: specific observer (username or ID)
   - Taxon: specific taxonomic group (taxon ID)
   - Quality: research grade, needs ID, casual, or all

4. **Select output fields**
   - Choose which fields to include in the output
   - Essential fields option available for common use

5. **Import data**
   - Click Import
   - Wait for completion
   - Two layers will be added to your project:
     - Main observations layer (points with all data)
     - Photos table (related photo URLs)

6. **Taxonomy enrichment** (optional)
   - Ensure the local database is installed
   - The taxonomy is added automatically during import
   - Seven taxonomic levels are added: kingdom, phylum, class, order, family, genus, species

### Date Filtering Options

Version 2.0.0 offers three date filtering modes:

- **Exact date**: Observations from a specific date
- **Date range**: Observations between two dates
- **Month filter**: All observations from a specific month across all years (useful for seasonal studies)

### Database Manager

Access via: Extensions → iNaturalist Import → Taxonomy Database Manager

Features:
- Download and install the local taxonomy database
- Check database status and version
- Update to newer versions when available
- View storage location and size

---

## Technical Details

### Dependencies

- **QGIS**: 3.40 or higher
- **Python**: 3.12
- **pyinaturalist**: Python library for iNaturalist API access

### Data Sources

- **Observations**: iNaturalist API (https://api.inaturalist.org)
- **Taxonomy**: Local database (1.4M taxa) or iNaturalist API

### Output Format

The plugin creates **two related layers** in GeoPackage format:

1. **Main observations layer** (point geometry)
   - Contains observation metadata, location, taxonomy
   - One point per observation
   - WGS84 coordinate system (EPSG:4326)

2. **Photos table** (no geometry)
   - Contains photo URLs and metadata
   - One-to-many relationship with observations
   - Multiple photos per observation properly handled
   - Linked via observation ID

This architecture improves data organization and allows proper handling of observations with multiple photos.

### Taxonomy Enrichment

The plugin uses a three-tier system:
1. Local database (when installed) - fastest
2. Persistent cache - for recently queried taxa
3. iNaturalist API - fallback for new taxa

---

## Compatibility

- **QGIS**: 3.40+ 
- **Operating Systems**: Windows, macOS, Linux
- **Tested on**: QGIS 3.40 (Bratislava) on Windows 10/11

---

## Troubleshooting

### Common Issues

**"Module 'pyinaturalist' not found"**
- Install using: `python -m pip install pyinaturalist`
- See installation instructions above

**"No observations found"**
- Check internet connection
- Verify coordinates are correct
- Try larger search radius
- Remove restrictive filters

**Slow taxonomy enrichment**
- Install the local database via Database Manager
- Check database installation status

**QGIS crashes**
- Update to latest QGIS version
- Reduce search radius for large datasets
- Select essential fields only

For other issues, please check the [issue tracker](https://github.com/yd73/iNaturalist_Import/issues).

---

## Contributing

Contributions are welcome. Please:
- Report bugs via GitHub Issues
- Suggest features via GitHub Issues
- Submit pull requests for code contributions

---

## License

This project is licensed under the GNU General Public License v3.0. See [LICENSE](LICENSE) for details.

### Third-Party Components

- **pyinaturalist**: MIT License
- **iNaturalist data**: Various Creative Commons licenses
- **QGIS**: GPL v2+

---

## Author

**Yves Durivault**
- Email: yves.durivault@gmail.com
- GitHub: [@yd73](https://github.com/yd73)

### Acknowledgments

- Perplexity AI for development assistance
- iNaturalist community for the biodiversity data
- QGIS development team

---

## Links

- **Repository**: https://github.com/yd73/iNaturalist_Import
- **Issues**: https://github.com/yd73/iNaturalist_Import/issues
- **iNaturalist**: https://www.inaturalist.org

---

## Notes

This plugin is independent of the existing "iNaturalist Extract" plugin. All internal names are prefixed with `yd_` to avoid conflicts.
