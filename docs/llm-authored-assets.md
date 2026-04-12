# LLM Authored Assets

This document describes how future LLM-generated content should enter `black-archive`.

The current project direction stays the same:

- the game runs in the CLI
- the current playable frontend is the ANSI HUD presentation layer
- the deterministic kernel owns state updates and rule execution
- authored JSON remains the default content source
- LLM content is optional and should enter through the same structured boundaries

## Purpose

LLM-generated content should help with:

- preparing upcoming nodes
- preparing arbitration scene details
- generating richer narration
- shaping long-term meta descriptions

LLM content should not replace the kernel's responsibility for:

- validating structure
- selecting legal state updates
- applying rule penalties
- keeping `Run`, `Node`, and `Arbitration` coherent

## Recommended Asset Types

### Campaign Pack

Structured campaign content for:

- map layout
- node ordering
- starting state
- high-level tone

### Node Pack

Structured node content for:

- node label
- map blurb
- linked arbitrations
- optional future preloaded flavor

### Arbitration Pack

Structured scene content for:

- scene summary
- player-facing question
- options
- tags
- authored effects

### Rule Pack

Structured rules that still map to `RuleTemplate`.

Use this for:

- temporary rule sets
- tone-specific rule variants
- campaign-specific pressure patterns

### Narration Pack

Structured narration templates for:

- opening
- judgement
- warning

Use this to vary presentation without overriding deterministic results.

## Required Boundaries

All LLM-authored assets should satisfy these rules:

### Structured First

- content must map to a known schema or internal dataclass shape
- free text alone is not enough

### Adapter First

- LLM output should enter through `state_adapter`
- the adapter should normalize fields, reject unknown structure, and fill safe defaults when appropriate

### Kernel Owns State Mutation

- LLM may propose content
- LLM may enrich descriptions
- LLM may preload future nodes
- LLM should not directly mutate `Run`, `Node`, `CoreStateView`, or `MetaStateView`

### Replayable

- generated content should be storable as JSON
- the same authored asset should be reusable for replay and debugging

## Recommended Flow

1. LLM generates a structured asset
2. `state_adapter` loads and normalizes it
3. the kernel validates shape and boundaries
4. runtime uses the validated object inside the normal `Run -> Node -> Arbitration` flow
5. narration may add flavor after the deterministic result is known

## Good Uses

- preloading the next two nodes based on `RunMemory`
- generating multiple arbitration scene drafts for a haunted district
- generating alternate narration packs for a campaign tone
- generating meta descriptions such as recent omens, fears, or recurring symbols

## Bad Uses

- letting LLM directly rewrite core stats
- letting LLM invent unsupported option effect fields at runtime
- bypassing `RuleTemplate` and injecting free-form rule text into selection
- replacing deterministic verdicts with raw LLM judgement

## Relation To The Current Repo

In the current project:

- `authoring` owns the authored JSON assets
- `state_adapter` is the loading and normalization boundary
- `runtime` consumes validated content
- `presentation` renders the current CLI HUD
- `rule_engine`, `enforcement`, and `memory` remain deterministic

So the intended long-term role of LLM is:

- content preparation
- world detail generation
- text enrichment
- future node and arbitration preloading

not direct kernel replacement
