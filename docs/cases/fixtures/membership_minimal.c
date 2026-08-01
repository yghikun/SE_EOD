/*
 * Synthetic FMPCA semantic fixture only.
 *
 * This file is not Linux or Btrfs evidence and must not be counted as a real
 * bug, evaluation case, or paper-validity result.
 */

#include <stdbool.h>

struct membership_member {
	unsigned int id;
};

struct membership_container {
	const struct membership_member *member;
	unsigned int count;
	bool isolated;
};

enum membership_path {
	PATH_NORMAL,
	PATH_ROLLBACK,
	PATH_VIOLATION,
	PATH_UNKNOWN_REPAIR,
};

typedef void (*unknown_repair_fn)(struct membership_container *container,
				  const struct membership_member *member);

static void acquire_isolation(struct membership_container *container)
{
	container->isolated = true;
}

static void release_isolation(struct membership_container *container)
{
	container->isolated = false;
}

static void add_member(struct membership_container *container,
		       const struct membership_member *member)
{
	container->member = member;
}

static void remove_member(struct membership_container *container,
			  const struct membership_member *member)
{
	if (container->member == member)
		container->member = 0;
}

static void adjust_count(struct membership_container *container, int delta)
{
	container->count += delta;
}

int membership_operation(struct membership_container *container,
			 const struct membership_member *member,
			 enum membership_path path,
			 unknown_repair_fn repair)
{
	acquire_isolation(container);
	add_member(container, member);

	switch (path) {
	case PATH_NORMAL:
		adjust_count(container, 1);
		release_isolation(container);
		return 0;
	case PATH_ROLLBACK:
		remove_member(container, member);
		release_isolation(container);
		return -1;
	case PATH_VIOLATION:
		release_isolation(container);
		return -1;
	case PATH_UNKNOWN_REPAIR:
		repair(container, member);
		release_isolation(container);
		return -1;
	}

	release_isolation(container);
	return -1;
}
