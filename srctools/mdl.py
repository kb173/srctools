"""Parses Source models, to extract metadata."""
from typing import Set, List, BinaryIO, NamedTuple
from enum import IntFlag

from srctools.filesys import FileSystem, File
from srctools import Vec
from struct import unpack, Struct, calcsize


IncludedMDL = NamedTuple('IncludedMDL', [
    ('label', str),
    ('filename', str),
])


class Flags(IntFlag):
    """Flags for studio models."""
    autogenerated_hitbox = 1 << 0
    uses_env_cubemap = 1 << 1
    force_opaque = 1 << 2
    translucent_twopass = 1 << 3
    static_prop = 1 << 4
    uses_fb_texture = 1 << 5
    hasshadowlod = 1 << 6
    uses_bumpmapping = 1 << 7
    use_shadowlod_materials = 1 << 8
    obsolete = 1 << 9
    unused = 1 << 10
    no_forced_fade = 1 << 11
    force_phoneme_crossfade = 1 << 12
    constant_directional_light_dot = 1 << 13
    flexes_converted = 1 << 14
    built_in_preview_mode = 1 << 15
    ambient_boost = 1 << 16
    do_not_cast_shadows = 1 << 17
    cast_texture_shadows = 1 << 18


def str_read(format, file: BinaryIO):
    """Read a structure from the file."""
    return unpack(format, file.read(calcsize(format)))


def read_nullstr(file: BinaryIO, pos: int=None):
    """Read a null-terminated string from the file."""
    if pos is not None:
        if pos == 0:
            return ''
        file.seek(pos)

    text = []
    while True:
        char = file.read(1)
        if char == b'\0':
            return b''.join(text).decode('ascii')
        if not char:
            raise ValueError('Fell off end of file!')
        text.append(char)


def read_nullstr_array(file: BinaryIO, count: int) -> List[str]:
    """Read consecutive null-terminated strings from the file."""
    arr = [None] * count  # type: List[str]
    if not count:
        return arr

    for i in range(count):
        arr[i] = read_nullstr(file)
    return arr


def read_offset_array(file: BinaryIO, count: int):
    """Read an array of offsets to null-terminated strings from the file."""
    cdmat_offsets = str_read(str(count) + 'i', file)
    arr = [None] * count  # type: List[str]

    for ind, off in enumerate(cdmat_offsets):
        file.seek(off)
        arr[ind] = read_nullstr(file)
    return arr
    
ST_VEC = Struct('fff')


def str_readvec(file: BinaryIO) -> Vec:
    """Read a vector from a file."""
    return Vec(ST_VEC.unpack(file.read(ST_VEC.size)))


class Model:
    def __init__(self, filesystem: FileSystem, file: File):
        """Parse a model from a file."""
        self._file = file
        self._sys = filesystem
        self.version = 49
        with self._sys, self._file.open_bin() as f:
            self._load(f)

    def _load(self, f: BinaryIO):
        """Read data from the MDL file."""
        assert f.tell() == 0, "Doesn't begin at start?"
        if f.read(4) != b'IDST':
            raise ValueError('Not a model!')
        (
            self.version,
            name,
            file_len,
            # 4 bytes are unknown...
        ) = str_read('i 4x 64s i', f)

        if not 44 <= self.version <= 49:
            raise ValueError('Unknown MDL version {}!'.format(self.version))

        self.name = name.rstrip(b'\0').decode('ascii')
        self.eye_pos = str_readvec(f)
        self.illum_pos = str_readvec(f)
        # Approx dimensions
        self.hull_min = str_readvec(f)
        self.hull_max = str_readvec(f)
        
        self.view_min = str_readvec(f)
        self.view_max = str_readvec(f)

        # Break up the reading a bit to limit the stack size.
        (
            flags,

            bone_count,
            bone_off,

            bone_controller_count, bone_controller_off,

            hitbox_count, hitbox_off,
            anim_count, anim_off,
            sequence_count, sequence_off,
        ) = str_read('11I', f)

        self.flags = Flags(flags)


        (
            activitylistversion, eventsindexed,

            texture_count, texture_offset,
            cdmat_count, cdmat_offset,
            
            skinref_count, skinref_ind, skinfamily_count,
            
            bodypart_count, bodypart_offset,
            attachment_count, attachment_offset,
        ) = str_read('13i', f)

        (
            localnode_count,
            localnode_index,
            localnode_name_index,
         
            # mstudioflexdesc_t
            flexdesc_count,
            flexdesc_index,
         
            # mstudioflexcontroller_t
            flexcontroller_count,
            flexcontroller_index,
         
            # mstudioflexrule_t
            flexrules_count,
            flexrules_index,
         
            # IK probably referse to inverse kinematics
            # mstudioikchain_t
            ikchain_count,
            ikchain_index,
         
            # Information about any "mouth" on the model for speech animation
            # More than one sounds pretty creepy.
            # mstudiomouth_t
            mouths_count, 
            mouths_index,
         
            # mstudioposeparamdesc_t
            localposeparam_count,
            localposeparam_index,
        ) = str_read('15I', f)

        # VDC:
        # For anyone trying to follow along, as of this writing,
        # the next "surfaceprop_index" value is at position 0x0134 (308)
        # from the start of the file.
        assert f.tell() == 308, 'Offset wrong? {} != 308 {}'.format(f.tell(), f)

        (
            # Surface property value (single null-terminated string)
            surfaceprop_index,
         
            # Unusual: In this one index comes first, then count.
            # Key-value data is a series of strings. If you can't find
            # what you're interested in, check the associated PHY file as well.
            keyvalue_index,
            keyvalue_count,	
         
            # More inverse-kinematics
            # mstudioiklock_t
            iklock_count,
            iklock_index,
        ) = str_read('5I', f)

        (
            self.mass,  # Mass of object (float)
            self.contents,  # ??

            # Other models can be referenced for re-used sequences and
            # animations
            # (See also: The $includemodel QC option.)
            # mstudiomodelgroup_t
            includemodel_count,
            includemodel_index,

            # In-engine, this is a pointer to the combined version of this +
            # included models. In the file it's useless.
            virtualModel,

            # mstudioanimblock_t
            animblocks_name_index,
            animblocks_count,
            animblocks_index,

            animblockModel,  # Placeholder for mutable-void*

            # Points to a series of bytes?
            bonetablename_index,

            vertex_base,  # Placeholder for void*
            offset_base,  # Placeholder for void*
        ) = str_read('f 11I', f)

        (
            # Used with $constantdirectionallight from the QC
            # Model should have flag #13 set if enabled
            directionaldotproduct,  # byte

            # Preferred rather than clamped
            rootLod,  # byte

            # 0 means any allowed, N means Lod 0 -> (N-1)
            self.numAllowedRootLods,  # byte

            #unknown byte;
            #unknown int;

            # mstudioflexcontrollerui_t
            flexcontrollerui_count,
            flexcontrollerui_index,
        ) = str_read('3b 5x 2I', f)

        # Build CDMaterials data
        f.seek(cdmat_offset)
        self.cdmaterials = read_offset_array(f, cdmat_count)
        
        for ind, cdmat in enumerate(self.cdmaterials):
            cdmat = cdmat.replace('\\', '/')
            if cdmat[-1:] != '/':
                cdmat += '/'
            self.cdmaterials[ind] = cdmat

        # All models fallback to checking the texture at a root folder.
        if '/' not in self.cdmaterials:
            self.cdmaterials.append('/')
        
        # Build texture data
        f.seek(texture_offset)
        self.textures = [None] * texture_count
        tex_temp = [None] * texture_count
        for tex_ind in range(texture_count):
            tex_temp[tex_ind] = (
                f.tell(),
                # Texture data:
                # int: offset to the string, from start of struct.
                # int: flags - appears to solely indicate 'teeth' materials...
                # int: used, whatever that means.
                # 4 unused bytes.
                # 2 4-byte pointers in studiomdl to the material class, for
                #      server and client - shouldn't be in the file...
                # 40 bytes of unused space (for expansion...)
                str_read('iii 4x 8x 40x', f)
            )
        for tex_ind, (offset, data) in enumerate(tex_temp):
            name_offset, flags, used = data
            f.seek(offset + name_offset)
            self.textures[tex_ind] = (
                read_nullstr(f),
                flags,
                used,
            )

        f.seek(surfaceprop_index)
        self.surfaceprop = read_nullstr(f)

        f.seek(keyvalue_index)
        self.keyvalues = read_nullstr_array(f, keyvalue_count)

        f.seek(includemodel_index)
        self.included_models = [None] * includemodel_count  # type: List[IncludedMDL]
        for i in range(includemodel_count):
            pos = f.tell()
            # This is two offsets from the start of the structures.
            lbl_pos, filename_pos = str_read('II', f)
            self.included_models[i] = IncludedMDL(
                read_nullstr(f, pos + lbl_pos) if lbl_pos else '',
                read_nullstr(f, pos + filename_pos) if filename_pos else '',
            )
            # Then return to after that struct - 4 bytes * 2.
            f.seek(pos + 4 * 2)

    def iter_textures(self, skins: Set[int]=None):
        """Yield textures used by this model.

        Skins if given should be a set of skin indexes, which constrains the
        list. This looks up in the filesystem to determine which CDMaterials
        folder to use, if any.
        """

        if skins:
            raise NotImplementedError('Skin families.')

        with self._sys:
            for tex in self.textures:
                tex_path = tex[0]
                for folder in self.cdmaterials:
                    full = 'materials/{}{}.vmt'.format(folder, tex_path)
                    if full in self._sys:
                        yield full
                        break