# Location data source

`locations.json` — Kenya's counties, sub-counties (constituencies) and wards,
per the IEBC administrative boundaries.

- 47 counties · 290 sub-counties · 1,451 wards (county codes 1–47).
- Sourced from the public dataset:
  https://github.com/michaelnjuguna/Kenyan-counties-their-subcounties-and-wards-in-json-yaml-mysql-csv-latex-xlsx-Bson-markdown-and-xml
  (file `county.json`), chosen after rejecting a rival dataset that was missing
  Nairobi, Bomet and Kericho and ~190 wards.
- Bundled rather than fetched from a live API: it changes only when IEBC
  redraws boundaries, and a school in a poor-signal area must still be able to
  register without depending on a third party being up.
