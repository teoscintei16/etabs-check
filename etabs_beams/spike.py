"""Spike etapa 0: conectare read-only la ETABS rulat, test GetAllFrames."""
import comtypes.client

def attach():
    try:
        obj = comtypes.client.GetActiveObject("CSI.ETABS.API.ETABSObject")
        return obj
    except Exception as e:
        print("GetActiveObject failed:", repr(e))
        return None

obj = attach()
if obj is None:
    raise SystemExit(1)
m = obj.SapModel
print("file:", m.GetModelFilename())
print("locked:", m.GetModelIsLocked())
print("units:", m.GetPresentUnits())
r = m.FrameObj.GetAllFrames()
print("GetAllFrames ret type/len:", type(r), len(r) if hasattr(r,'__len__') else r)
print(r[:3] if hasattr(r,'__getitem__') else r)
