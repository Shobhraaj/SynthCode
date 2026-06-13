from backend.app.services.sampler import FileSampler, TreeEntry


def test_sampler_filters_generated_and_vendor_files():
    tree = [
        TreeEntry(path="src/app.py", type="blob", size=400, sha="a"),
        TreeEntry(path="node_modules/pkg/index.js", type="blob", size=500, sha="b"),
        TreeEntry(path="dist/bundle.min.js", type="blob", size=5000, sha="c"),
        TreeEntry(path="README.md", type="blob", size=1000, sha="d"),
        TreeEntry(path="src/tiny.ts", type="blob", size=100, sha="e"),
    ]

    selected = FileSampler().sample(tree, max_files=30)

    assert [entry.path for entry in selected] == ["src/app.py"]


def test_sampler_respects_max_files():
    tree = [
        TreeEntry(path=f"src/file_{index}.py", type="blob", size=500 + index, sha=str(index))
        for index in range(50)
    ]

    selected = FileSampler().sample(tree, max_files=30)

    assert len(selected) == 30

