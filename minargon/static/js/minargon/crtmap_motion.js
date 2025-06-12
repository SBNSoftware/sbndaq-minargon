console.log("../../static/js/minargon/crtmap_motion.js loaded!");

//map section
const section = document.getElementById('crtmap-section');

//3D models
const cube = document.querySelector('.cube');
const cubeContainer = document.querySelector('.cube-container');
const resetButton = document.getElementById('reset-button');


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



async function loadCubeConfig() {
    const response = await fetch(FEBjsonURL);
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



function createCubeFacesRt(FEBs, TextRotation, ModuleRotation) {
    FEBs.forEach(module => {
        const faceElement = document.createElement('div');
        faceElement.classList.add('module', module.FEB);
		faceElement.style.width = `${module.dimensionW}px`;
		faceElement.style.height = `${module.dimensionH}px`;

        // Add link and text
        const link = document.createElement('a');
        link.href = 'empty'; //module.linkUrl;
        link.textContent = 'F'+module.FEB;
        link.style.fontSize = '60px';
        link.style.color = 'white';

        //Modifications based on FEB group
        //Translate the top-left corner to the destinated location
        let Tx = -module.CoMx - module.dimensionW/2 ;
        let Ty = -module.CoMy - module.dimensionH/2 ;
        let Tz = -module.CoMz;

       
        let transformStr = `translateX(${Tx}px) translateY(${Ty}px) translateZ(${Tz}px)`;
        //X: left-->right Y: down-->up Z: s-->N
        if( TextRotation !=="") {link.style.transform = TextRotation;} 
        if( ModuleRotation !=="") {transformStr += ModuleRotation;}
		
        faceElement.style.transform = transformStr;
        faceElement.style.backgroundColor = 'rgba(0, 0, 0, 0.65)';
        faceElement.style.border = '2px solid red';

        cube.appendChild(faceElement);
        faceElement.appendChild(link);

		/*console.log("\nFEB: " + module.FEB);
        console.log("width: " + face.dimensionW);
        console.log("height: " + face.dimensionH);
        console.log("ymax: " + (Ty));
        console.log("transform: ", transformStr);*/
    });
}



loadCubeConfig();
