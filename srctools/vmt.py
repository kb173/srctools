"""Parses material files."""
from typing import Iterable, List, Dict, Union

import sys
from enum import Enum

from srctools import FileSystem, Property
from srctools.tokenizer import Token as Tok, Tokenizer as Tokenizer


class VarType(Enum):
    """The different types shader variables can be.

    The value is the name used in the game code.
    """
    # Vars like $selfillum which set a bitmask - these cannot be altered later.
    FLAG = 0

    MATERIAL = 'SHADER_PARAM_TYPE_MATERIAL'  # models/blah.vmt
    STR = 'SHADER_PARAM_TYPE_STRING' # Basic string, nothing special.
    TEXTURE = 'SHADER_PARAM_TYPE_TEXTURE'

    INT = 'SHADER_PARAM_TYPE_INTEGER'
    FLOAT = 'SHADER_PARAM_TYPE_FLOAT'  # 4.0, .3, 2.3f
    BOOL = 'SHADER_PARAM_TYPE_BOOL'  # 0, 1

    COLOR = 'SHADER_PARAM_TYPE_COLOR'  # RGBA, optional A
    VEC2 = 'SHADER_PARAM_TYPE_VEC2'  # [0 0]
    VEC3 = 'SHADER_PARAM_TYPE_VEC3'  # [0 0 0]
    VEC4 = 'SHADER_PARAM_TYPE_VEC4'  # [0 0 0 0]

    # Transformation matrix in the following forms:
    # 'center .5 .5 scale 1 1 rotate 0 translate 0 0'
    # '[1 0 0 0 1 0 0 0 1]'
    MATRIX = 'SHADER_PARAM_TYPE_MATRIX'  # 9-matrix, or center scale rotate etc

    #ENVMAP = 'SHADER_PARAM_TYPE_ENVMAP' # Obsolete apparently
    # Special case - pointer to arbitrary shader-specific data.
    FOUR_CC = 'SHADER_PARAM_TYPE_FOURCC'


class Material:
    """Represents a material.
    
    Attributes:
        shader: The name of the shader.
        proxies: List of Material Proxies defined for the material. 
            Each is a tuple of the string name and a dict of keys-> values.
            "Empty" proxies are removed.
    """
    def __init__(
        self, 
        shader: str, 
        params: Dict[str, Union[str, Property]],
        proxies: List[Property],
    ):
        """Create a material."""
        self.shader = shader
        self._params = params
        self.proxies = proxies
    
    @classmethod
    def parse(cls, data: Iterable[str], filename: str=''):
        """Parse a VMT from the file. 
        
        """
        tok = Tokenizer(data, filename, string_bracket=True)
        
        # First look for the shader name -
        # which must be the first string
        # in the file.
        shader_name = None
        for token, shader_name in tok:
            if token is Tok.NEWLINE:
                continue
            elif token is Tok.STRING:
                break
            else:
                raise tok.error(token)

        if not shader_name:
            raise tok.error("No shader name!")

        # Open the parameters body.
        tok.expect(Tok.BRACE_OPEN)
        
        params = {}
        proxies = []
        
        # Look for parameter names
        for token, param_name in tok:
            if token is Tok.NEWLINE:
                continue
            # End of body.
            elif token is Tok.BRACE_CLOSE:
                break
            elif token is Tok.PROP_FLAG:
                tok.expect(Tok.NEWLINE)
                continue
            elif token is not Tok.STRING:
                raise tok.error(token)
            token, param_value = tok()
            
            if token is Tok.STRING:
                # We have the value.
                pass
            elif token is Tok.NEWLINE:
                # Name by itself: '%compilenodraw' etc...
                param_value = None
                # We need to check there's a newline after that - for proxies, 
                # or errors.
                token, ignored = tok()
                if token is Tok.BRACE_OPEN:
                    if param_name.casefold() == "proxies":
                        proxies.extend(cls._parse_block(tok, 'Proxy'))
                    else:
                        params[
                            param_name.casefold()
                        ] = cls._parse_block(tok, param_name)

                    continue  # Don't replace with None.
                elif token is Tok.BRACE_CLOSE:
                    # End of us after single name.
                    params[param_name.casefold()] = param_value
                    break
                else:
                    raise tok.error(token)
            else:
                raise tok.error(token)
                
            params[param_name.casefold()] = param_value
             
        # We expect nothing else now.
        tok.expect(Tok.EOF)
        
        return cls(shader_name, params, proxies)

    @staticmethod
    def _parse_proxies(tok: Tokenizer):
        # Parse the proxy block.

        for token, proxy_name in tok.skipping_newlines():
            if token is Tok.BRACE_CLOSE:
                return
            elif token is not Tok.STRING:
                raise tok.error(token)

            opts = {}

            tok.expect(Tok.BRACE_OPEN)  # Start of proxy values.

            # Looking for key-value parameters for a proxy
            for token, param_name in tok.skipping_newlines():
                if token is Tok.BRACE_CLOSE:
                    break
                elif token is not Tok.STRING:
                    raise tok.error(token)

                token, param_value = tok()

                if token is Tok.STRING:
                    opts[param_name.casefold()] = param_value
                else:
                    raise tok.error(token)
            else:
                raise tok.error('EOF while reading options for "{}" proxy', proxy_name)
            yield proxy_name, opts
        else:
            raise tok.error('Proxy block not closed!')

    @staticmethod
    def _parse_block(tok: Tokenizer, name: str) -> Property:
        """Parse a block into a block of properties."""
        prop = Property(name, [])

        for token, param_name in tok:
            # End of our block
            if token is Tok.BRACE_CLOSE:
                return prop
            elif token is Tok.NEWLINE:
                continue
            elif token is not Tok.STRING:
                raise tok.error(token)

            token, param_value = tok()

            if token is Tok.STRING:
                # We have the value.
                pass
            elif token is Tok.NEWLINE:
                # Name by itself: '%compilenodraw' etc...
                # We need to check there's a newline after that - for subblocks.
                token, ignored = tok()
                if token is Tok.BRACE_OPEN:
                    prop.append(Material._parse_block(tok, param_name))
                    continue
                elif token is Tok.NEWLINE:
                    pass
                elif token is Tok.BRACE_CLOSE:
                    # End of us after single name.
                    prop.append(Property(param_name, ''))
                    break
                else:
                    raise tok.error(token)
            else:
                raise tok.error(token)
            prop.append(Property(param_name, param_value))

        raise tok.error('EOF without closed block!')

    def apply_patches(self, fsys: FileSystem, limit=100) -> 'Material':
        """If the file is a Patch shader expand to the full material.

        This reads from the supplied filesystem as needed. If more than
        limit files are parsed, a RecursionError is raised.
        """
        return self._apply_patch(fsys, 1, limit)

    def _apply_patch(self, fsys: FileSystem, count: int, limit: int) -> 'Material':
        """Do apply_patches()."""
        if count > limit:
            raise RecursionError('Parsed too deep a Patch tree!')

        if self.shader.casefold() != 'patch':
            return self

        try:
            filename = self._params['include']
        except KeyError:
            raise ValueError('No "include" key for Patch shader!') from None
        try:
            parent_file = fsys[filename]
        except FileNotFoundError:
            raise ValueError(
                'Material file "{}" does not exist when'
                ' patching!'.format(filename)
            ) from None

        with fsys, parent_file.open_str() as f:
            parent = Material.parse(f, filename)

        parent = parent._apply_patch(fsys, count + 1, limit)

        new_params = {
            name: (prop.copy() if isinstance(prop, Property) else prop)
            for name, prop in parent._params.items()
        }

        for prop in self._params.get('insert', ()):
            if prop.has_children():
                raise ValueError('Append contains blocks?')
            new_params[prop.name] = prop.value

        return Material(
            parent.shader,
            new_params,
            [
                prox.copy()
                for prox in
                parent.proxies
            ]
        )
