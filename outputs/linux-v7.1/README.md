# Linux v7.1 Results

Place Linux v7.1 scan artifacts under one directory per filesystem:

```text
outputs/linux-v7.1/
  ext4/
  btrfs/
  xfs/
  f2fs/
```

Use `--linux linux-sources/linux-v7.1-fs` and write all `--*-out` paths below
`outputs/linux-v7.1/<filesystem>/` so they remain separate from v6.8 results.
