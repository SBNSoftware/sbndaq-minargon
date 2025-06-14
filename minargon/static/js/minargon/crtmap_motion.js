//map section
const section = document.getElementById('crtmap-section');
let isMouseInside = false;

//scene-wrapper for scaling
const sceneWrapper = document.querySelector('.scene-wrapper');

//3D models
const cube = document.querySelector('.cube');
const cubeContainer = document.querySelector('.cube-container');

//button
const resetButton = document.getElementById('reset-button');

//arrow for the compass at the bottom corner
const compassFrame = document.querySelector('.compass-container');
const arrow = document.querySelector('.arrow-container');

//Motions variables
let isDragging = false;
let startX, startY;
let rotationX = 0, rotationY = 0;
let zoomLevel = parseFloat(getComputedStyle(sceneWrapper).getPropertyValue('--zoom')) || 0.3;
let zoom_min = 0.05;
let zoom_max = 2;


//if scroll into the map section, 
//Mark mouse enter event
section.addEventListener('mouseenter', () => {
  isMouseInside = true;
  });
  section.addEventListener('mouseleave', () => {
    isMouseInside = false;
	});


////show compass
const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach(entry => {
        arrow.style.display = entry.isIntersecting ? 'block' : 'none';
        compassFrame.style.display = entry.isIntersecting ? 'block' : 'none';
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


//    const crtSp = config.AllFEB.filter(item =>  (item.FEB === 166 || item.FEB===61|| item.FEB===135) ) ;
//    createCubeFacesRt(crtSp,  '                        ', '               '); // TextRotation & ModuleRotation
}



function createCubeFacesRt(FEBs, TextRotation, ModuleRotation) {
    FEBs.forEach(module => {
        const faceElement = document.createElement('div');
        faceElement.classList.add('module', module.FEB);
		faceElement.style.width = `${module.dimensionW}px`;
		faceElement.style.height = `${module.dimensionH}px`;

        // Add link and text
        const link = document.createElement('a');
        link.href = "CRT_board_snapshot?board_no="+module.FEB; //module.linkUrl;
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

		cube.appendChild(faceElement);
		faceElement.appendChild(link);

		/*
		console.log("\nFEB: " + module.FEB);
		  console.log("width: " + module.dimensionW);
		  console.log("height: " + module.dimensionH);
		  console.log("ymax: " + (Ty));
		  console.log("transform: ", transformStr);
		  */
	});
}

// Start dragging
document.addEventListener('mousedown', (e) => {
		isDragging = true;
		startX = e.clientX;
		startY = e.clientY;
		});


// Dragging
document.addEventListener('mousemove', (e) => {
		if (!isDragging) return;

		const deltaX = e.clientX - startX;
		const deltaY = e.clientY - startY;

		//rotationX -= deltaY * 0.5; // Adjust sensitivity with multiplier
		//rotationY += deltaX * 0.5;

		rotationX = Math.max(-90, Math.min(90, rotationX - deltaY * 0.5)); // Clamp rotationX
		rotationY += deltaX * 0.5;

		//Aids for the arrow compass
		//onCubeRotationUpdate(rotationX, rotationY);
		arrow.style.transform = `rotateX(${rotationX}deg) rotateY(${rotationY}deg)`;

		cube.style.transform = `rotateX(${rotationX}deg) rotateY(${rotationY}deg)`;

		startX = e.clientX;
		startY = e.clientY;
		});

// Stop dragging
document.addEventListener('mouseup', () => {
		isDragging = false;
		});

// Optional: Stop dragging when the mouse leaves the window
document.addEventListener('mouseleave', () => {
		isDragging = false;
		});

// Reset button functionality
resetButton.addEventListener('click', () => {
		rotationX = 0;
		rotationY = 0;
		cube.style.transform = `rotateX(${rotationX}deg) rotateY(${rotationY}deg)`;
	});

// Zoom in/out on scroll
document.addEventListener('wheel', (e) => {
		if( !isMouseInside) return;
		e.preventDefault();

		const delta = Math.sign(e.deltaY);
		zoomLevel += delta * -0.04;
		zoomLevel = Math.min(Math.max(zoomLevel, zoom_min ), zoom_max); // Clamp zoom level between 0.05 and 2
		// Update only the scale via CSS variable
		sceneWrapper.style.setProperty('--zoom', zoomLevel);
		}, {passive: false} );

loadCubeConfig();
