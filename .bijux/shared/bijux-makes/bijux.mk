BIJUX_MAKES_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
BIJUX_MAKES_SHARED_ROOT ?= $(abspath $(BIJUX_MAKES_DIR)/..)
BIJUX_MAKE_COMPONENTS ?=
BIJUX_MAKE_KNOWN_COMPONENTS := docs rust node
BIJUX_MAKE_UNKNOWN_COMPONENTS := $(filter-out $(BIJUX_MAKE_KNOWN_COMPONENTS),$(BIJUX_MAKE_COMPONENTS))

ifneq ($(strip $(BIJUX_MAKE_UNKNOWN_COMPONENTS)),)
$(error unsupported BIJUX_MAKE_COMPONENTS: $(BIJUX_MAKE_UNKNOWN_COMPONENTS))
endif

include $(BIJUX_MAKES_DIR)/environment.mk
include $(BIJUX_MAKES_DIR)/guards.mk

ifneq ($(filter docs,$(BIJUX_MAKE_COMPONENTS)),)
include $(BIJUX_MAKES_DIR)/docs.mk
endif

ifneq ($(filter rust,$(BIJUX_MAKE_COMPONENTS)),)
BIJUX_MAKES_RS_DIR ?= $(BIJUX_MAKES_SHARED_ROOT)/bijux-makes-rs
include $(BIJUX_MAKES_RS_DIR)/bijux.mk
endif

ifneq ($(filter node,$(BIJUX_MAKE_COMPONENTS)),)
BIJUX_MAKES_NODE_DIR ?= $(BIJUX_MAKES_SHARED_ROOT)/bijux-makes-node
include $(BIJUX_MAKES_NODE_DIR)/workspace.mk
endif

include $(BIJUX_MAKES_DIR)/entrypoints.mk
include $(BIJUX_MAKES_DIR)/ci.mk
include $(BIJUX_MAKES_DIR)/help.mk
