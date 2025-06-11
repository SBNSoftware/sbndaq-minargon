console.log("../../static/js/minargon/crtmap_motion.js loaded!");

//map section
const section = document.getElementById('crtmap-section');


//arrow for the compass at the bottom corner
const arrow = document.querySelector('.arrow-container');

//if scroll into the map section, show compass
const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach(entry => {
        arrow.style.display = entry.isIntersecting ? 'block' : 'none';
      });
    },
    {
      root: null,       // viewport
      threshold: 0.1    // 10% of section visible triggers it
    }
  );
observer.observe(section);


//Load CRT modules
async function loadCubeConfig() {
    const response = await fetch('cubeConfig.json');
    const config = await response.json();
    //createCubeFaces(config.AllFEB);

    const crtTH = config.AllFEB.filter(item => item.group === "Top High");
    const crtTL = config.AllFEB.filter(item => item.group === "Top Low");
    const crtE = config.AllFEB.filter(item => item.group === "East");
    const crtW = config.AllFEB.filter(item => item.group === "West");
    const crtN = config.AllFEB.filter(item => item.group === "North");
    const crtS = config.AllFEB.filter(item => item.group === "South");
    const crtB = config.AllFEB.filter(item => (item.group === "Bottom" && item.CoMy < -381.5) || item.group === "MINOS" ||  item.FEB === 82 );
    const crtBB = config.AllFEB.filter(item => item.group === "Bottom" && item.CoMy > -381.5 && item.FEB !== 82);
    

    /* createCubeFaces(crtTH);*/
    createCubeFacesRt(crtTH, '                        ', 'rotateX(90deg)'); // TextRotation & ModuleRotation
    createCubeFacesRt(crtTL, 'rotate(90deg)           ', 'rotateX(90deg)'); // TextRotation & ModuleRotation
    createCubeFacesRt(crtW,  'scaleX(-1)              ', 'rotateY(90deg)'); // TextRotation & ModuleRotation
    createCubeFacesRt(crtE,  '                        ', 'rotateY(90deg)'); // TextRotation & ModuleRotation
    createCubeFacesRt(crtN,  'scaleX(-1)              ', '               '); // TextRotation & ModuleRotation
    createCubeFacesRt(crtS,  '                        ', '               '); // TextRotation & ModuleRotation
    createCubeFacesRt(crtB,  'rotate(180deg) scaleX(-1)', 'rotateX(90deg)'); // TextRotation & ModuleRotation
    createCubeFacesRt(crtBB, 'rotate(90deg)           ', 'rotateX(90deg)'); // TextRotation & ModuleRotation
}




loadCubeConfig();
