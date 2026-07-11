#include <stdio.h>

struct root {
	const char *name;
	int refs;
	struct root *reloc_root;
	int in_rc_list;
};

static struct root *btrfs_grab_root(struct root *root)
{
	root->refs++;
	return root;
}

static void btrfs_put_root(struct root *root)
{
	root->refs--;
}

static void __del_reloc_root(struct root *reloc_root)
{
	if (reloc_root->in_rc_list) {
		reloc_root->in_rc_list = 0;
		btrfs_put_root(reloc_root);
	}
}

static void free_reloc_control(struct root *reloc_root)
{
	__del_reloc_root(reloc_root);
}

static void clean_dirty_subvols(struct root *fs_root)
{
	if (fs_root->reloc_root) {
		btrfs_put_root(fs_root->reloc_root);
		fs_root->reloc_root = NULL;
	}
}

int main(void)
{
	struct root fs_root = { .name = "fs_root", .refs = 1 };
	struct root reloc_root = {
		.name = "reloc_root",
		.refs = 1,
		.in_rc_list = 1,
	};

	fs_root.reloc_root = btrfs_grab_root(&reloc_root);
	printf("after grab: reloc_refs=%d fs_root.reloc_root=%p\n",
	       reloc_root.refs, (void *)fs_root.reloc_root);

	/* Model btrfs_commit_transaction(trans) failure going to out_unset. */
	free_reloc_control(&reloc_root);
	printf("after out_unset cleanup: reloc_refs=%d fs_root.reloc_root=%p\n",
	       reloc_root.refs, (void *)fs_root.reloc_root);

	/* Model the normal successful path that reaches clean_dirty_subvols(). */
	clean_dirty_subvols(&fs_root);
	printf("after clean_dirty_subvols: reloc_refs=%d fs_root.reloc_root=%p\n",
	       reloc_root.refs, (void *)fs_root.reloc_root);

	return reloc_root.refs == 1 ? 23 : 0;
}
