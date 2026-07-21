# MOCC-SE Discovery Version Matrix

This is a development comparison across source versions, not a frozen benchmark.

Versions:

- `v6.8`: candidates=19, unknown=2, report=`outputs/mocc-discovery-v1-linux-v6.8.json`
- `v6.14`: candidates=20, unknown=2, report=`outputs/mocc-discovery-v1-linux-v6.14.json`
- `v7.1`: candidates=14, unknown=3, report=`outputs/mocc-discovery-v1-linux-v7.1.json`

Function matrix:

| protocol | function | v6.8 | v6.14 | v7.1 |
|---|---|---|---|---|
| mocc.protocol_a.replay_recovery | ext4_fc_replay_add_range | C5/R0/U0 | C5/R0/U0 | C5/R0/U0 |
| mocc.protocol_a.replay_recovery | ext4_fc_replay_del_range | C3/R0/U0 | C3/R0/U0 | C3/R0/U0 |
| mocc.protocol_a.replay_recovery | ext4_fc_replay_inode | C5/R0/U0 | C5/R0/U0 | C0/R0/U1 |
| mocc.protocol_a.replay_recovery | xfs_rtcopy_summary | C2/R0/U0 | C2/R0/U0 | C0/R0/U0 |
| mocc.protocol_a.replay_recovery | xfs_rtginode_ensure | C0/R0/U0 | C1/R0/U0 | C2/R0/U0 |
| mocc.protocol_b.device_topology_rollback | btrfs_recover_relocation | C1/R0/U0 | C1/R0/U0 | C1/R0/U0 |
| mocc.protocol_b.device_topology_rollback | btrfs_init_new_device | C1/R0/U1 | C1/R0/U1 | C1/R0/U1 |
| mocc.protocol_c.activation_accounting | reserve_chunk_space | C1/R0/U1 | C1/R0/U1 | C1/R0/U1 |
| mocc.protocol_c.activation_accounting | ext4_expand_extra_isize_ea | C1/R0/U0 | C1/R0/U0 | C1/R0/U0 |

Development deltas:

- removed/cleared candidate functions: `ext4_fc_replay_inode`, `xfs_rtcopy_summary`
- added candidate functions: `xfs_rtginode_ensure`
