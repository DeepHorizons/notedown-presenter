import enum
import io
import os
import nbformat as nbformat
import nbformat.v4.nbbase as nbbase
from notedown.notedown import MarkdownReader, MarkdownWriter
from notedown.main import markdown_template
#from notedown.contentsmanager import NotedownContentsManager


class MarkdownPresenterReader(MarkdownReader):
    class SlideTypes(enum.Enum):
        slide = 'slide'
        subslide = 'subslide'
        fragment = 'fragment'
        skip = 'skip'  # Not used yet
        speakernotes = 'notes'  # Not used yet

    slide_type = 'slide_type'

    def parse_blocks(self, text):
        all_blocks = super().parse_blocks(text)

        # If the block is markdown, then we need to do further processing
        # Three empty newlines (Four newlines): Make a new block and say its a slide
        # Two empty newlines (Three newlines): Make a new block and say its a sub-slide
        # One empty newline (two newlines): Make a new block and say its a fragment
        processed_blocks = []
        for block in all_blocks:
            if block['type'] == 'markdown':
                content = block['content']
                print(f"block: `{content.encode()}`")
                next_type = self.SlideTypes.slide
                last_index = 0
                last_index_check = 0

                # We look for a newline
                current_index = content.find('\n')
                current_skip = content.find('-skip-')
                while current_index >= 0:
                    if current_skip >= 0 and current_index > current_skip:
                        # We need to evaluate the skip first
                        end_skip = content.find('-skip-', current_skip+1)
                        current_string = content[current_skip+6:end_skip].strip()
                        b = block.copy()
                        b['content'] = current_string
                        b[self.slide_type] = self.SlideTypes.skip
                        processed_blocks.append(b)
                        # 8 = len('-skip-\n') + 1
                        current_index = end_skip + 5
                        # Find the next non \n character
                        #while content[current_index] == '\n':
                        #    current_index += 1
                        last_index = current_index + 1
                        if current_index >= len(content):
                            break
                        current_skip = content.find('-skip-', end_skip+1)
                    elif content[current_index + 1] == '\n':
                        if content[current_index + 2] == '\n':
                            if content[current_index + 3] == '\n':
                                # Next data will be a new slide
                                current_string = content[last_index:current_index]
                                b = block.copy()
                                b['content'] = current_string
                                b[self.slide_type] = next_type
                                # TODO sometimes we get blank cells ONLY IN NOTEBOOKS
                                if current_string:
                                    processed_blocks.append(b)
                                next_type = self.SlideTypes.slide
                                current_index += 3
                                last_index = current_index + 1
                            else:
                                # Next data will be a sub slide
                                current_string = content[last_index:current_index]
                                b = block.copy()
                                b['content'] = current_string
                                b[self.slide_type] = next_type
                                # TODO sometimes we get blank cells ONLY IN NOTEBOOKS
                                if current_string:
                                    processed_blocks.append(b)
                                next_type = self.SlideTypes.subslide
                                current_index += 2
                                last_index = current_index + 1
                        else:
                            # Next data will be a fragment
                            current_string = content[last_index:current_index]
                            b = block.copy()
                            b['content'] = current_string
                            b[self.slide_type] = next_type
                            # TODO sometimes we get blank cells ONLY IN NOTEBOOKS
                            if current_string:
                                processed_blocks.append(b)
                            next_type = self.SlideTypes.fragment
                            current_index += 1
                            last_index = current_index + 1
                    last_index_check = current_index
                    current_index = content.find('\n', last_index_check+1)

                # Take care of the last block
                current_string = content[last_index:]
                b = block.copy()
                b['content'] = current_string
                b[self.slide_type] = next_type
                processed_blocks.append(b)
            elif block['type'] == 'code':
                # TODO The writer inserts a newline in the begining, we should fix that
                block['content'] = block['content'].strip()
                processed_blocks.append(block)
            else:
                processed_blocks.append(block)

        return processed_blocks

    @staticmethod
    def create_markdown_cell(block):
        """Create a markdown cell from a block."""
        kwargs = {'cell_type': block['type'],
                  'source': block['content']}
        if MarkdownPresenterReader.slide_type in block:
            kwargs['metadata'] = {'slideshow': {MarkdownPresenterReader.slide_type: block[MarkdownPresenterReader.slide_type].value}}
        markdown_cell = nbbase.new_markdown_cell(**kwargs)
        return markdown_cell

    @staticmethod
    def create_code_cell(block):
        """Create a notebook code cell from a block."""

        # All code should be subslides
        metadata = {'slideshow': {MarkdownPresenterReader.slide_type: MarkdownPresenterReader.SlideTypes.subslide.value}}
        code_cell = nbbase.new_code_cell(source=block['content'], metadata=metadata)

        attr = block['attributes']
        if not attr.is_empty:
            code_cell.metadata.update(nbbase.NotebookNode({'attributes': attr.to_dict()}))
            execution_count = attr.kvs.get('n')
            if not execution_count:
                code_cell.execution_count = None
            else:
                code_cell.execution_count = int(execution_count)

        return code_cell


class MarkdownPresenterWriter(MarkdownWriter):
    def writes(self, notebook):
        for cell in notebook.cells[1:]:
            if 'metadata' in cell and 'slideshow' in cell['metadata']:
                slide_type = cell['metadata']['slideshow']['slide_type']
                # The exporter will already insert two newlines for each new cell, so we
                if slide_type == MarkdownPresenterReader.SlideTypes.slide.value:
                    cell['source'] = '\n\n' + cell['source'].strip()
                elif slide_type == MarkdownPresenterReader.SlideTypes.subslide.value:
                    cell['source'] = '\n' + cell['source'].strip()
                elif slide_type == MarkdownPresenterReader.SlideTypes.fragment.value:
                    cell['source'] = '' + cell['source'].strip()
                elif slide_type == MarkdownPresenterReader.SlideTypes.skip.value:
                    cell['source'] = '-skip-\n' + cell['source'].strip() + '\n-skip-'
        return super().writes(notebook)

import os
import nbformat
from tornado import web

try:
    import notebook.transutils
    from notebook.services.contents.filemanager import FileContentsManager
except ImportError:
    from IPython.html.services.contents.filemanager import FileContentsManager

from notedown.main import ftdetect


class NotedownPresenterContentsManager(FileContentsManager):
    """Subclass the IPython file manager to use markdown
    as the storage format for notebooks.

    Intercepts the notebook before read and write to determine the
    storage format from the file extension (_read_notebook and
    _save_notebook).

    We have to override the get method to treat .md as a notebook
    file extension. This is the only change to that method.

    To use, add the following line to ipython_notebook_config.py:

      c.NotebookApp.contents_manager_class = 'notedown.NotedownContentsManager'

    Now markdown notebooks can be opened and edited in the browser!
    """
    strip_outputs = False

    def convert(self, content, informat, outformat, strip_outputs=False):
        if os.path.exists(content):
            with io.open(content, 'r', encoding='utf-8') as f:
                contents = f.read()
        else:
            contents = content

        readers = {'notebook': nbformat,
                   'markdown': MarkdownPresenterReader(precode='',
                                                       magic=False,
                                                       match='fenced')
                   }

        writers = {'notebook': nbformat,
                   'markdown': MarkdownPresenterWriter(markdown_template,
                                              strip_outputs=strip_outputs)
                   }

        reader = readers[informat]
        writer = writers[outformat]

        notebook = reader.reads(contents, as_version=4)
        import logging
        logging.basicConfig()
        logging.error(notebook)
        return writer.writes(notebook)

    def _read_notebook(self, os_path, as_version=4):
        """Read a notebook from an os path."""
        with self.open(os_path, 'r', encoding='utf-8') as f:
            try:
                if ftdetect(os_path) == 'notebook':
                    return nbformat.read(f, as_version=as_version)
                elif ftdetect(os_path) == 'markdown':
                    nbjson = self.convert(os_path,
                                     informat='markdown',
                                     outformat='notebook')
                    return nbformat.reads(nbjson, as_version=as_version)
            except Exception as e:
                raise web.HTTPError(
                    400,
                    u"Unreadable Notebook: %s %r" % (os_path, e),
                )

    def _save_notebook(self, os_path, nb):
        """Save a notebook to an os_path."""
        with self.atomic_writing(os_path, encoding='utf-8') as f:
            if ftdetect(os_path) == 'notebook':
                nbformat.write(nb, f, version=nbformat.NO_CONVERT)
            elif ftdetect(os_path) == 'markdown':
                nbjson = nbformat.writes(nb, version=nbformat.NO_CONVERT)
                markdown = self.convert(nbjson,
                                   informat='notebook',
                                   outformat='markdown',
                                   strip_outputs=self.strip_outputs)
                f.write(markdown)

    def get(self, path, content=True, type=None, format=None):
        """ Takes a path for an entity and returns its model

        Parameters
        ----------
        path : str
            the API path that describes the relative path for the target
        content : bool
            Whether to include the contents in the reply
        type : str, optional
            The requested type - 'file', 'notebook', or 'directory'.
            Will raise HTTPError 400 if the content doesn't match.
        format : str, optional
            The requested format for file contents. 'text' or 'base64'.
            Ignored if this returns a notebook or directory model.

        Returns
        -------
        model : dict
            the contents model. If content=True, returns the contents
            of the file or directory as well.
        """
        path = path.strip('/')

        if not self.exists(path):
            raise web.HTTPError(404, u'No such file or directory: %s' % path)

        os_path = self._get_os_path(path)
        extension = ('.ipynb', '.md')

        if os.path.isdir(os_path):
            if type not in (None, 'directory'):
                raise web.HTTPError(400,
                                    u'%s is a directory, not a %s' % (path,
                                                                      type),
                                    reason='bad type')
            model = self._dir_model(path, content=content)

        elif type == 'notebook' or (type is None and path.endswith(extension)):
            model = self._notebook_model(path, content=content)
        else:
            if type == 'directory':
                raise web.HTTPError(400,
                                    u'%s is not a directory' % path,
                                    reason='bad type')
            model = self._file_model(path, content=content, format=format)
        return model


if __name__ == '__main__':
    a = MarkdownPresenterReader(precode='', magic=False, match='fenced')
    b = MarkdownPresenterWriter(markdown_template, strip_outputs=False)
    print(f"template: `{markdown_template}`")
    code = """
# This is a test!
testing presentation



## New slide
This is a new slide
* list in the side

* fragment list



## Code
Here is some code
```c
int i;
```


## Some questions
* Why?
* There should be a space between this and `skip`

-skip-
The next cell depends on the spacing above this
-----
Quiz question
x answer
-----
-----
Another quiz question
* a
* b
x c
-----
-skip-


### Sub slide
* Why not?



## Questions?

"""

    notebook = a.reads(code, as_version=4)
    print(notebook)
    print(b.writes(notebook))
