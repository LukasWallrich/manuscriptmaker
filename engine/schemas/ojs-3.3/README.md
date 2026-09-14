# OJS 3.3 native import schema

The schemas are from OJS tag `3_3_0-15` and its pinned PKP library submodule
`5cad3a1534781d682b242b528158b957702948f1`:

- https://github.com/pkp/ojs/blob/3_3_0-15/plugins/importexport/native/native.xsd
- https://github.com/pkp/pkp-lib/blob/5cad3a1534781d682b242b528158b957702948f1/plugins/importexport/native/pkp-native.xsd
- https://github.com/pkp/pkp-lib/blob/5cad3a1534781d682b242b528158b957702948f1/xml/importexport.xsd

Only relative include paths are changed so validation works offline. These
third-party schema files retain their GPL v3 licence; see COPYING. They are
not covered by this repository's MIT licence.

Schema validity does not establish compatibility with a particular journal's
section labels, user groups, uploader account or configured genres. Test an
import in a staging copy of the target OJS instance before production use.
