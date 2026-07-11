struct super_block;
struct buffer_head;
struct mutex;
typedef unsigned long size_t;
typedef void handle_t;
typedef struct {
	int a_version;
} ext4_acl_header;
typedef struct {
	int e_tag;
} ext4_acl_entry_short;
struct posix_acl {
	int dummy;
};
struct demo_holder {
	struct buffer_head *bh;
};
struct base_holder {
	void *base;
};
struct fs_context {
	void *fs_private;
};
struct kmem_cache;

int foo(void);
struct buffer_head *sb_bread(struct super_block *sb, int block);
void brelse(struct buffer_head *bh);
void put_bh(struct buffer_head *bh);
handle_t *ext4_journal_start(struct super_block *sb, int type, int blocks);
int ext4_journal_stop(handle_t *handle);
int IS_ERR(const void *ptr);
int PTR_ERR(const void *ptr);
void *ERR_PTR(int err);
int cpu_to_le32(int value);
int ext4_acl_count(size_t size);
struct posix_acl *posix_acl_alloc(int count, int flags);
void kfree(const void *ptr);
void *kmalloc(size_t size, int flags);
void *kzalloc(size_t size, int flags);
void *kmem_cache_alloc(struct kmem_cache *cache, int flags);
void kmem_cache_free(struct kmem_cache *cache, void *ptr);
void kobject_put(void *ptr);
void ext4_fc_free(struct fs_context *fc);
void mutex_lock(struct mutex *lock);
void mutex_unlock(struct mutex *lock);

#define EXT4_ACL_VERSION 1
#define GFP_NOFS 0
#define EINVAL 22
#define ENOMEM 12

int demo_ret_return(void)
{
	int ret;

	ret = foo();
	if (ret) return ret;
	return 0;
}

int demo_goto_out(void)
{
	int ret;

	ret = foo();
	if (ret) goto out;
	return 0;
out:
	return ret;
}

int demo_goto_brelse(struct super_block *sb)
{
	struct buffer_head *bh;
	int ret;

	bh = sb_bread(sb, 1);
	if (!bh)
		return -EIO;

	ret = foo();
	if (ret) goto out_brelse;

	brelse(bh);
	return 0;

out_brelse:
	brelse(bh);
	return ret;
}

int demo_null_bh(struct super_block *sb)
{
	struct buffer_head *bh;

	bh = sb_bread(sb, 2);
	if (!bh) return -EIO;
	brelse(bh);
	return 0;
}

int demo_missing_brelse(struct super_block *sb)
{
	struct buffer_head *bh;
	int ret;

	bh = sb_bread(sb, 3);
	if (!bh)
		return -EIO;

	ret = foo();
	if (ret) return ret;

	brelse(bh);
	return 0;
}

int demo_goto_out_missing_brelse(struct super_block *sb)
{
	struct buffer_head *bh;
	int ret;

	bh = sb_bread(sb, 4);
	if (!bh)
		return -EIO;

	ret = foo();
	if (ret) goto out;

	brelse(bh);
	return 0;
out:
	return ret;
}

int demo_wrapper_possible(struct super_block *sb)
{
	struct buffer_head *bh;
	int ret;

	bh = sb_bread(sb, 8);
	if (!bh)
		return -EIO;

	ret = foo();
	if (ret) goto out_put;

	brelse(bh);
	return 0;
out_put:
	put_bh(bh);
	return ret;
}

int demo_ownership_transfer_hint(struct super_block *sb, struct demo_holder *holder)
{
	struct buffer_head *bh;
	int ret;

	bh = sb_bread(sb, 9);
	if (!bh)
		return -EIO;

	holder->bh = bh;
	ret = foo();
	if (ret) return ret;

	brelse(bh);
	return 0;
}

int demo_error_swallowed(void)
{
	int ret;

	ret = foo();
	if (ret) goto out;
	return 0;
out:
	return 0;
}

int demo_partial_cleanup(struct super_block *sb, struct mutex *lock)
{
	struct buffer_head *bh;
	int ret;

	mutex_lock(lock);
	bh = sb_bread(sb, 5);
	if (!bh)
		return -EIO;

	ret = foo();
	if (ret) goto out_brelse;

	brelse(bh);
	mutex_unlock(lock);
	return 0;

out_brelse:
	brelse(bh);
	return ret;
}

int demo_missing_mutex_unlock(struct mutex *lock)
{
	int ret;

	mutex_lock(lock);
	ret = foo();
	if (ret) return ret;

	mutex_unlock(lock);
	return 0;
}

int demo_handle_is_err(struct super_block *sb)
{
	handle_t *handle;

	handle = ext4_journal_start(sb, 0, 1);
	if (IS_ERR(handle)) return PTR_ERR(handle);

	ext4_journal_stop(handle);
	return 0;
}

int demo_missing_journal_stop(struct super_block *sb)
{
	handle_t *handle;
	int ret;

	handle = ext4_journal_start(sb, 0, 1);
	if (IS_ERR(handle))
		return PTR_ERR(handle);

	ret = foo();
	if (ret) return ret;

	ext4_journal_stop(handle);
	return 0;
}

int demo_field_alias_cleanup(struct base_holder *s)
{
	int ret;

	s->base = kzalloc(4096, GFP_NOFS);
	if (s->base == NULL)
		goto out;

	ret = foo();
	if (ret)
		goto cleanup;

	kfree(s->base);
	return 0;
cleanup:
	kfree(s->base);
	return ret;
out:
	return -ENOMEM;
}

int demo_array_element_cleanup(struct super_block *sb, struct buffer_head **bhs)
{
	int ret, i = 0;

	bhs[i] = sb_bread(sb, 10);
	if (!bhs[i])
		return -EIO;

	ret = foo();
	if (ret)
		goto out;

	brelse(bhs[i]);
	return 0;
out:
	brelse(bhs[i]);
	return ret;
}

int demo_kmem_cache_free_second_arg(struct kmem_cache *cache)
{
	void *node;
	int ret;

	node = kmem_cache_alloc(cache, GFP_NOFS);
	if (!node)
		return -ENOMEM;

	ret = foo();
	if (ret)
		goto out;

	kmem_cache_free(cache, node);
	return 0;
out:
	kmem_cache_free(cache, node);
	return ret;
}

int demo_kobject_put_cleanup(void)
{
	void *ext4_feat;
	int ret;

	ext4_feat = kzalloc(32, GFP_NOFS);
	if (!ext4_feat)
		return -ENOMEM;

	ret = foo();
	if (ret)
		goto out;

	kfree(ext4_feat);
	return 0;
out:
	kobject_put(ext4_feat);
	return ret;
}

int demo_ext4_fc_free_cleanup(struct fs_context *fc)
{
	void *s_ctx;
	int ret;

	s_ctx = kzalloc(64, GFP_NOFS);
	if (!s_ctx)
		goto out;

	fc->fs_private = s_ctx;
	ret = foo();
	if (ret)
		goto out_free;

	ext4_fc_free(fc);
	return 0;
out_free:
	ext4_fc_free(fc);
	return ret;
out:
	return -ENOMEM;
}

void *demo_null_eq_goto_acquire_failure(void)
{
	void *flex_gd;

	flex_gd = kmalloc(128, GFP_NOFS);
	if (flex_gd == NULL)
		goto out;

	return flex_gd;
out:
	return NULL;
}

int demo_nested_if_not_outer_error(int len)
{
	void *node;

	if (len > 4) {
		node = kmalloc(32, GFP_NOFS);
		if (!node)
			return -ENOMEM;
		kfree(node);
	}
	return 0;
}

struct posix_acl *ext4_acl_from_disk_like(const void *value, size_t size)
{
	const char *end = (char *)value + size;
	int n, count;
	struct posix_acl *acl;

	if (!value)
		return NULL;
	if (size < sizeof(ext4_acl_header))
		return ERR_PTR(-EINVAL);
	if (((ext4_acl_header *)value)->a_version !=
	    cpu_to_le32(EXT4_ACL_VERSION))
		return ERR_PTR(-EINVAL);

	count = ext4_acl_count(size);
	if (count < 0)
		return ERR_PTR(-EINVAL);
	if (count == 0)
		return NULL;

	acl = posix_acl_alloc(count, GFP_NOFS);
	if (!acl)
		return ERR_PTR(-ENOMEM);

	for (n = 0; n < count; n++) {
		if ((char *)value + sizeof(ext4_acl_entry_short) > end)
			goto fail;
		value = (char *)value + sizeof(ext4_acl_entry_short);
	}

	return acl;

fail:
	kfree(acl);
	return ERR_PTR(-EINVAL);
}
