# npm local security repack

`npm-12.2.2-dafeiyu.1.tgz` is an explicitly modified npm 12.2.2 build, versioned `12.2.2+dafeiyu.1`. The npm CLI source is unchanged. The dependency graph is unbundled and its glob/minimatch requirements use the patched releases. All transitive packages are recorded in the parent package-lock.json.

Reproduce and verify with `python3 scripts/repack_npm.py --check`. The pinned upstream URL/SHA512 and local SHA256 are in provenance.json. The archive retains npm's Artistic-2.0 LICENSE and DAFEIYU-REPACK-NOTICE.txt, with the standard upstream version's download address and exact modifications. The companion's MIT license does not replace npm's upstream license.
