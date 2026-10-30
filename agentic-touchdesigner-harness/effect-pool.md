# The effect pool — workspace structure

The harness's TouchDesigner workspace is a single project
organized as an **effect pool**: instead of one project per
effect, every TouchDesigner-side effect is a top-level
component in one file, driven through the one file bridge.

```
/project1
  fx_blobtrack/            one component per effect
    blobnet/               the blob-track instancing network
      src                  movie input
      matte_level          contrast stage of the tracking matte
      matte_thr            threshold stage
      blobtrack            the Blob Track operator
      blobinfo             its table, as an Info DAT
      bassdata             baked bass envelope (text)
      frameidx             current capture frame (text)
      basssrc              envelope -> CHOP
      instancer            blob table + bass -> instance channels
      geo                  instanced rectangles (instancing ON)
      cam / render         orthographic render, working size
      blob_layer           layer output (over the matte null)
      filebridge           the bridge Execute DAT lives in
                           whichever component hosts it
  fx_pseudograph/          reserved slot: the pseudo-graph
                           effect's future TD home (the
                           current implementation is external,
                           see the pseudo-graph shelf)
```

Rules of the pool:

- The shipped build script creates the network as
  `/project1/blobnet` in a fresh project; the pool
  organization wraps that same component as
  `fx_blobtrack/blobnet`, which requires rewriting the
  network's absolute internal paths to the new location
  (a mechanical pass — the callbacks address the network
  by absolute path). The bridge's host component is a
  parameter for exactly this reason.

- **One bridge for the whole pool.** The bridge DAT sits in
  one host component and can reach every other component by
  path; adding an effect never adds a control channel.
- **Components are self-contained.** An effect component
  owns its inputs, parameters, and outputs; the pool file
  can be saved under a new name and every component comes
  with it.
- **Build scripts are the source of truth.** A component
  that cannot be rebuilt from a script in this repository
  does not belong in the pool — the binary is a workspace,
  not an archive. That is why the `.toe` itself is not
  published: `build_blob_network.py` regenerates the
  blob-track component, and future components land with
  their own build scripts.
- **Session state is not content.** A live session's save
  pointer, backups, and rotation files are operational
  details of the machine it runs on; they stay there.
