#include <stdio.h>
#include <string.h>

#define BTRFS_MAX_LEVEL 8
#define BTRFS_READ_LOCK 1

struct extent_buffer {
	int lock_held;
	int refs;
};

struct btrfs_path {
	struct extent_buffer *nodes[BTRFS_MAX_LEVEL];
	int slots[BTRFS_MAX_LEVEL];
	int locks[BTRFS_MAX_LEVEL];
	int nowait;
	int skip_locking;
	int bad_unlocks;
};

static void btrfs_tree_unlock_rw(struct btrfs_path *path, int level)
{
	if (!path->nodes[level]->lock_held)
		path->bad_unlocks++;
	else
		path->nodes[level]->lock_held = 0;
}

static void free_extent_buffer(struct extent_buffer *eb)
{
	eb->refs--;
}

static void btrfs_release_path(struct btrfs_path *p)
{
	for (int i = 0; i < BTRFS_MAX_LEVEL; i++) {
		p->slots[i] = 0;
		if (!p->nodes[i])
			continue;
		if (p->locks[i]) {
			btrfs_tree_unlock_rw(p, i);
			p->locks[i] = 0;
		}
		free_extent_buffer(p->nodes[i]);
		p->nodes[i] = NULL;
	}
}

static void unlock_up(struct btrfs_path *path, int level, int lowest_unlock)
{
	int skip_level = level;
	int check_skip = 1;

	for (int i = level; i < BTRFS_MAX_LEVEL; i++) {
		if (!path->nodes[i])
			break;
		if (!path->locks[i])
			break;

		if (check_skip) {
			if (path->slots[i] == 0) {
				skip_level = i + 1;
				continue;
			}
		}

		if (i >= lowest_unlock && i > skip_level) {
			check_skip = 0;
			btrfs_tree_unlock_rw(path, i);
			path->locks[i] = 0;
		}
	}
}

static int btrfs_try_tree_read_lock(struct extent_buffer *eb)
{
	(void)eb;
	return 0;
}

static int model_btrfs_next_old_leaf_nowait(struct btrfs_path *path,
					    struct extent_buffer *next,
					    struct extent_buffer *lower)
{
	int level = 2;
	int ret;

	while (1) {
		level--;
		path->nodes[level] = next;
		path->slots[level] = 0;
		if (!path->skip_locking)
			path->locks[level] = BTRFS_READ_LOCK;
		if (!level)
			break;

		next = lower;
		if (!path->skip_locking && path->nowait) {
			if (!btrfs_try_tree_read_lock(next)) {
				ret = -11;
				goto done;
			}
		}
	}
	ret = 0;
done:
	unlock_up(path, 0, 1);
	return ret;
}

int main(void)
{
	struct btrfs_path path;
	struct extent_buffer parent = { .lock_held = 1, .refs = 1 };
	struct extent_buffer next = { .lock_held = 1, .refs = 1 };
	struct extent_buffer lower = { .refs = 1 };
	int ret;

	memset(&path, 0, sizeof(path));
	path.nowait = 1;
	path.nodes[2] = &parent;
	path.locks[2] = BTRFS_READ_LOCK;
	path.slots[2] = 1;

	ret = model_btrfs_next_old_leaf_nowait(&path, &next, &lower);
	printf("ret=%d node1=%p lock1=%d lower_in_path=%s lower_refs=%d bad_unlocks=%d\n",
	       ret, (void *)path.nodes[1], path.locks[1],
	       path.nodes[1] == &lower ? "yes" : "no", lower.refs,
	       path.bad_unlocks);

	btrfs_release_path(&path);
	printf("after_release bad_unlocks=%d lower_refs=%d\n",
	       path.bad_unlocks, lower.refs);

	return lower.refs ? 23 : 0;
}
